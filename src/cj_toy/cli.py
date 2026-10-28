"""데모와 명령행 인터페이스. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""

import argparse
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from .client import AddressRefineError, CJClient, DuplicateBookingError
from .config import Config
from .constants import ADDRESS_API, API_PATHS, BOOK_API, CANCEL_API, INVOICE_API, TOKEN_API
from .logging_utils import configure, mask
from .mock_server import MockServer
from .models import Item, Party, Shipment
from .service import ShipmentService

SAMPLE_ADDRESS = '서울특별시 중구 세종대로 110'


class DemoRecorder(logging.Handler):
    """데모에 필요한 API 결과를 메모리에서 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        """정형 로그의 필드를 수집한다."""
        self.records.append({'event': record.getMessage(), **getattr(record, 'fields', {})})

    def last_result(self, api: str) -> dict[str, Any]:
        """마지막 정상 응답의 내용을 반환한다."""
        return next(
            entry['response'] for entry in reversed(self.records)
            if entry['event'] == 'api_response' and entry.get('api') == api
        )


def sample(order: str = 'SAMPLE-001', address: str = SAMPLE_ADDRESS) -> Shipment:
    """개인정보가 아닌 예제 배송 요청을 만든다."""
    sender = Party('홍길동', '010-0000-0000', '04524', SAMPLE_ADDRESS, '테스트 1층')
    receiver = Party('김철수', '010-0000-0000', '04524', address, '테스트 2층')
    return Shipment(order, sender, receiver, [Item('테스트 상품', 2)], remark='문 앞에 놓아 주세요')


def _say(message: str) -> None:
    print(message, flush=True)


def _print_booking(result: Any, recorder: DemoRecorder) -> None:
    label = result.label
    _say(f'  {result.cust_use_no}: 주소 정제 성공')
    _say(f'    CLSFCD={label["CLSFCD"]}, SUBCLSFCD={label["SUBCLSFCD"]}')
    _say(f'    CLLDLVBRANNM={label["CLLDLVBRANNM"]}')
    _say(f'    CLLDLVEMPNICKNM={label["CLLDLVEMPNICKNM"]}, P2PCD={label["P2PCD"]}')
    _say(f'    채번 INVC_NO={result.invc_no}')
    _say(f'    RegBook RESULT_CD={recorder.last_result(BOOK_API)["RESULT_CD"]}')


def demo() -> None:
    """로컬 서버에서 접수부터 오류 및 추적까지 시연한다."""
    Path('out').mkdir(exist_ok=True)
    logger = configure('out/demo.log', stderr=True)
    recorder = DemoRecorder()
    logger.addHandler(recorder)
    if os.getenv('CJ_BASE_URL') not in (None, '', 'http://127.0.0.1:8765'):
        raise ValueError('demo는 자동 시작한 로컬 mock에서만 실행할 수 있습니다. CJ_BASE_URL을 비우세요.')
    customer = os.getenv('CJ_CUST_ID', 'MOCK_CUSTOMER')
    biz = os.getenv('CJ_BIZ_REG_NUM', '0000000000')
    server = MockServer(('127.0.0.1', 0), customer, biz)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = Config(
        customer, biz, f'http://127.0.0.1:{server.server_port}', timeout=0.1, auth_retry_wait=0,
    )
    try:
        store = Path('out/demo-bookings.json')
        store.unlink(missing_ok=True)
        other = Path('out/demo-other-bookings.json')
        other.unlink(missing_ok=True)
        client = CJClient(config, retry_base=0.02)
        service = ShipmentService(client, store, 'out')
        _say('1. 정상 접수 2건: 주소 정제 → 채번 → 접수 → 라벨')
        first = service.create_shipment(sample('DEMO-001'))
        _print_booking(first, recorder)
        second = service.create_shipment(sample('DEMO-002'))
        _print_booking(second, recorder)
        before = sum(server.calls.values())
        again = service.create_shipment(sample('DEMO-001'))
        after = sum(server.calls.values())
        _say(f'2. 멱등 재요청: INVC_NO={again.invc_no}, CJ 호출 전={before}, 후={after}')
        _say(f'   추가 호출={after - before}회')
        before_invoice = server.calls.get(INVOICE_API, 0)
        try:
            service.create_shipment(sample('DEMO-BAD', '분석불가 테스트 주소'))
        except AddressRefineError as exc:
            count = server.calls.get(INVOICE_API, 0) - before_invoice
            _say(f'3. 주소정제 실패: RESULT_CD={exc.result_cd}, 채번 추가 호출={count}회')
        _say('4. 일시적 오류 재시도')
        for kind in ('500', 'delay'):
            start = len(recorder.records)
            server.fail_next(ADDRESS_API, kind)
            client.refine_address(SAMPLE_ADDRESS)
            for entry in recorder.records[start:]:
                if entry['event'] == 'api_retry':
                    _say(f'   attempt={entry["attempt"]} 실패 원인={entry["reason"]}, 재시도')
                elif entry['event'] == 'api_response' and entry['attempt'] > 1:
                    _say(f'   attempt={entry["attempt"]} 결과={entry["result_cd"]}')
        before_tokens = server.calls.get(TOKEN_API, 0)
        server.expire_token()
        client.refine_address(SAMPLE_ADDRESS)
        after_tokens = server.calls.get(TOKEN_API, 0)
        _say(f'5. 토큰 만료 E401: 발급 전={before_tokens}회, 후={after_tokens}회')
        _say(f'   재발급={after_tokens - before_tokens}회, 주소정제 성공')
        try:
            ShipmentService(client, other, 'out').create_shipment(sample('DEMO-001'))
        except DuplicateBookingError as exc:
            _say(f'6. 원격 중복: RESULT_CD={exc.result_cd}, RESULT_DETAIL={exc.detail}')
        service.cancel_shipment('DEMO-002')
        _say(f'7. 예약 취소: DEMO-002, RESULT_CD={recorder.last_result(CANCEL_API)["RESULT_CD"]}')
        events = service.track(first.invc_no)
        _say(f'8. 운송장 {first.invc_no} 추적')
        _say('   CRG_ST | 상태 | 처리일 | 처리시간 | 처리점소')
        for event in events:
            _say(
                f'   {event["CRG_ST"]} | {event["CRG_ST_NM"]} | {event["SCAN_YMD"]} | '
                f'{event["SCAN_HOUR"]} | {event["DEALT_BRAN_NM"]}'
            )
        _say('API별 호출 횟수 (mock 서버 기준)')
        for api in API_PATHS:
            _say(f'   {api:<18} {server.calls.get(api, 0)}회')
        _say('라벨: out/labels.json, out/labels.csv, out/label_<운송장>.html')
        _say('주의: 레이아웃 가정 (CJ 표준 운송장 가이드 미확인)')
        _say('구조화 로그: stderr 및 out/demo.log (마스킹 적용)')
    finally:
        logger.removeHandler(recorder)
        server.shutdown()
        server.server_close()


def _real_tracking(invoice: str) -> None:
    from .public_tracking import track

    labels = {
        'get_status': '진입 페이지 GET HTTP 상태',
        'csrf_acquired': '_csrf 획득 여부',
        'post_status': 'tracking-detail POST HTTP 상태',
    }

    def report(key: str, value: Any) -> None:
        """실제 HTTP 단계의 상태를 표시한다."""
        _say(f'{labels[key]}: {value}')

    events = track(invoice, report=report)
    _say(f'이벤트 개수: {len(events)}')
    _say('정규화 결과 (crgNm 제외): ' + json.dumps(events, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    """명령행 인수를 처리하고 종료 코드를 반환한다."""
    parser = argparse.ArgumentParser(description='CJ 택배 표준 API 토이')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo')
    ship = sub.add_parser('ship')
    ship.add_argument('--sample', action='store_true', required=True)
    cancel = sub.add_parser('cancel')
    cancel.add_argument('cust_use_no')
    tracking = sub.add_parser('track')
    tracking.add_argument('invoice')
    public = sub.add_parser('real-tracking')
    public.add_argument('invoice')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            demo()
            return 0
        if args.command == 'real-tracking':
            _real_tracking(args.invoice)
            return 0
        configure()
        service = ShipmentService(CJClient(Config.from_env()))
        if args.command == 'ship':
            result = service.create_shipment(sample())
            print(f'접수 완료: {result.invc_no}')
        elif args.command == 'cancel':
            service.cancel_shipment(args.cust_use_no)
            print('취소 완료')
        else:
            print(json.dumps(mask(service.track(args.invoice)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f'오류: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0
