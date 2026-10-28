"""로컬 CJ API 모의 서버. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""

import argparse
import datetime as dt
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .constants import (
    ADDRESS_API, ADDRESS_ERRORS, BOOK_API, CANCEL_API, DUPLICATE_DETAIL, INVOICE_API,
    RESULT_ERROR, RESULT_SUCCESS, TOKEN_API, TRACK_API,
)

BOOK_REQUIRED = (
    'CUST_ID', 'RCPT_YMD', 'CUST_USE_NO', 'RCPT_DV', 'WORK_DV_CD', 'REQ_DV_CD',
    'MPCK_KEY', 'CAL_DV_CD', 'FRT_DV_CD', 'CNTR_ITEM_CD', 'BOX_TYPE_CD', 'BOX_QTY',
    'CUST_MGMT_DLCM_CD', 'SENDR_NM', 'SENDR_TEL_NO1', 'SENDR_TEL_NO2', 'SENDR_TEL_NO3',
    'SENDR_ZIP_NO', 'SENDR_ADDR', 'SENDR_DETAIL_ADDR', 'RCVR_NM', 'RCVR_TEL_NO1',
    'RCVR_TEL_NO2', 'RCVR_TEL_NO3', 'RCVR_ZIP_NO', 'RCVR_ADDR', 'RCVR_DETAIL_ADDR',
    'PRT_ST', 'DLV_DV', 'ARRAY',
)
REQUIRED_FIELDS = {
    ADDRESS_API: ('CLNTNUM', 'CLNTMGMCUSTCD', 'ADDRESS'),
    INVOICE_API: ('CLNTNUM',),
    TRACK_API: ('CLNTNUM', 'INVC_NO'),
    BOOK_API: BOOK_REQUIRED,
    CANCEL_API: BOOK_REQUIRED,
}
ADDRESS_TRIGGERS = {'분석불가': '-20002', '권역없음': '-20003', '배송불가': '-20009'}


class MockServer(ThreadingHTTPServer):
    """격리된 상태와 장애 주입 기능을 가진 HTTP 서버."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int] = ('127.0.0.1', 8765),
        cust_id: str = 'MOCK_CUSTOMER',
        biz_reg_num: str = '0000000000',
    ) -> None:
        super().__init__(address, Handler)
        self.cust_id = cust_id
        self.biz_reg_num = biz_reg_num
        self.lock = threading.RLock()
        self.token: str | None = None
        self.token_time = 0.0
        self.counter = 650000000000
        self.bookings: dict[tuple[str, ...], dict[str, Any]] = {}
        self.calls: dict[str, int] = {}
        self.faults: dict[str, list[Any]] = {}
        self.delay_seconds = 0.2
        self.token_serial = 0

    def fail_next(self, api: str, kind: str, count: int = 1) -> None:
        """특정 API의 다음 요청에 지정된 장애를 주입한다."""
        with self.lock:
            self.faults[api] = [kind, count]

    def expire_token(self) -> None:
        """현재 토큰을 폐기해 다음 인증 요청을 실패시킨다."""
        with self.lock:
            self.token = None


class Handler(BaseHTTPRequestHandler):
    """명세 형식의 요청과 가상 응답을 처리한다."""

    server: MockServer

    def log_message(self, format: str, *args: Any) -> None:
        """기본 HTTP 접근 로그를 출력하지 않는다."""

    def reply(self, status: int, data: dict[str, Any]) -> None:
        """JSON 응답을 전송한다."""
        raw = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def error_response(self, status: int, detail: str) -> None:
        """게이트웨이 오류 형식으로 응답한다."""
        self.reply(status, {'RESULT_CD': f'E{status}', 'RESULT_DETAIL': detail})

    def do_POST(self) -> None:
        """API별 검증과 요청 처리를 수행한다."""
        api = self.path.strip('/')
        server = self.server
        with server.lock:
            server.calls[api] = server.calls.get(api, 0) + 1
            fault = server.faults.get(api)
            kind = fault[0] if fault else None
            if fault:
                fault[1] -= 1
                if fault[1] <= 0:
                    del server.faults[api]
        if kind == 'delay':
            time.sleep(server.delay_seconds)
        if kind in ('500', '429'):
            return self.error_response(int(kind), 'injected fault')
        if kind == '401':
            return self.error_response(401, 'Authentication failed')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size > 1000000:
                raise ValueError()
            data = json.loads(self.rfile.read(size))['DATA']
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            return self.error_response(400, 'DATA')
        with server.lock:
            self._dispatch(api, data)

    def _dispatch(self, api: str, data: dict[str, Any]) -> None:
        server = self.server
        if api == TOKEN_API:
            return self._issue_token(data)
        if (not server.token or self.headers.get('CJ-Gateway-APIKey') != server.token
                or data.get('TOKEN_NUM') != server.token):
            return self.error_response(401, 'Authentication failed')
        if api not in REQUIRED_FIELDS:
            return self.error_response(404, 'Unknown API')
        for key in REQUIRED_FIELDS[api]:
            if data.get(key) in (None, '', []):
                return self.error_response(400, key)
        if api in (BOOK_API, CANCEL_API):
            if not isinstance(data['ARRAY'], list) or any(
                not isinstance(item, dict) or not item.get('GDS_NM') or not item.get('MPCK_SEQ')
                for item in data['ARRAY']
            ):
                return self.error_response(400, 'ARRAY.GDS_NM / MPCK_SEQ')
            if data['CUST_ID'] != server.cust_id:
                return self.error_response(403, 'CUST_ID')
        if api in (ADDRESS_API, INVOICE_API, TRACK_API) and data['CLNTNUM'] != server.cust_id:
            if api == ADDRESS_API:
                return self.reply(200, {
                    'RESULT_CD': '-20001', 'RESULT_DETAIL': ADDRESS_ERRORS['-20001'],
                })
            return self.error_response(403, 'CLNTNUM')
        if api == ADDRESS_API:
            return self._address(data)
        if api == INVOICE_API:
            server.counter += 1
            return self.reply(200, {
                'RESULT_CD': RESULT_SUCCESS, 'RESULT_DETAIL': 'Success.',
                'DATA': {'INVC_NO': str(server.counter)},
            })
        if api in (BOOK_API, CANCEL_API):
            return self._booking(api, data)
        self._tracking(data)

    def _issue_token(self, data: dict[str, Any]) -> None:
        server = self.server
        for key in ('CUST_ID', 'BIZ_REG_NUM'):
            if not data.get(key):
                return self.error_response(400, key)
        now = time.monotonic()
        if now - server.token_time < 1:
            return self.error_response(429, 'token rate limit')
        server.token_time = now
        if data['CUST_ID'] != server.cust_id or data['BIZ_REG_NUM'] != server.biz_reg_num:
            return self.reply(200, {
                'RESULT_CD': RESULT_ERROR,
                'RESULT_DETAIL': '택배 계약 내역이 존재하지 않습니다. 재 확인 요청 드립니다',
            })
        if not server.token:
            server.token_serial += 1
            server.token = f'MOCK-TOKEN-{server.token_serial:08d}'
        expires = (dt.datetime.now() + dt.timedelta(hours=24)).strftime('%Y%m%d%H%M%S')
        self.reply(200, {
            'RESULT_CD': RESULT_SUCCESS, 'RESULT_DETAIL': 'Success.',
            'DATA': {'TOKEN_NUM': server.token, 'TOKEN_EXPRTN_DTM': expires},
        })

    def _address(self, data: dict[str, Any]) -> None:
        address = data['ADDRESS']
        if len(address) > 100:
            return self.error_response(400, 'ADDRESS')
        for trigger, code in ADDRESS_TRIGGERS.items():
            if trigger in address:
                return self.reply(200, {'RESULT_CD': code, 'RESULT_DETAIL': trigger})
        code = hashlib.sha256(address.encode()).hexdigest()[:4].upper()
        result = {
            'CLSFCD': code, 'SUBCLSFCD': '1g', 'CLSFADDR': '테스트 권역',
            'CLLDLVBRANNM': '테스트 집배점', 'CLLDLVEMPNM': '홍길동',
            'CLLDLVEMPNICKNM': 'G03-01', 'RSPSDIV': '01', 'P2PCD': 'P001',
        }
        self.reply(200, {'RESULT_CD': RESULT_SUCCESS, 'RESULT_DETAIL': 'Success.', 'DATA': result})

    def _booking(self, api: str, data: dict[str, Any]) -> None:
        key = tuple(data[field] for field in ('CUST_ID', 'RCPT_YMD', 'CUST_USE_NO', 'MPCK_KEY'))
        if api == BOOK_API:
            if key in self.server.bookings:
                return self.reply(200, {
                    'RESULT_CD': RESULT_ERROR, 'RESULT_DETAIL': DUPLICATE_DETAIL,
                })
            self.server.bookings[key] = {'data': data.copy(), 'cancelled': False, 'scanned': False}
        else:
            booking = self.server.bookings.get(key)
            if (not booking or booking['cancelled'] or booking['scanned']
                    or data['REQ_DV_CD'] != '02'):
                return self.reply(200, {
                    'RESULT_CD': RESULT_ERROR, 'RESULT_DETAIL': '취소할 수 없는 예약입니다.',
                })
            booking['cancelled'] = True
        self.reply(200, {'RESULT_CD': RESULT_SUCCESS, 'RESULT_DETAIL': 'Success.'})

    def _tracking(self, data: dict[str, Any]) -> None:
        booking = next((
            item for item in self.server.bookings.values()
            if item['data'].get('INVC_NO') == data['INVC_NO'] and not item['cancelled']
        ), None)
        if not booking:
            return self.error_response(404, '운송장을 찾을 수 없습니다')
        booking['scanned'] = True
        events = [
            {
                'INVC_NO': data['INVC_NO'], 'CRG_ST': code, 'CRG_ST_NM': name,
                'SCAN_YMD': '20260101', 'SCAN_HOUR': '120000', 'DEALT_BRAN_NM': '테스트 집배점',
                'DEALT_BRAN_TEL': '02-0000-0000', 'DEALT_EMP_NM': '홍길동',
                'DEALT_EMP_TEL': '010-0000-0000', 'ACPTR_NM': '김철수',
            }
            for code, name in [('11', '집화'), ('41', '간선'), ('82', '배송출발'), ('91', '배송완료')]
        ]
        self.reply(200, {'RESULT_CD': RESULT_SUCCESS, 'RESULT_DETAIL': 'Success.', 'DATA': events})


def main() -> None:
    """환경변수의 고객 정보로 로컬 서버를 실행한다."""
    from .config import Config

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    config = Config.from_env()
    server = MockServer(('127.0.0.1', args.port), config.cust_id, config.biz_reg_num)
    print(f'mock 서버: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
