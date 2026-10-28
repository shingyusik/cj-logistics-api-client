"""CJ API 요청 및 토큰 관리. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""

import datetime as dt
import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import Config
from .constants import (
    ADDRESS_API, ADDRESS_ERRORS, AUTH_ERROR, BOOK_API, CANCEL_API, DUPLICATE_DETAIL,
    INVOICE_API, RESULT_GATEWAY_SUCCESS, RESULT_SUCCESS, TOKEN_API, TRACK_API,
)


class CJApiError(Exception):
    """CJ API가 반환한 오류 코드와 상세 내용."""

    def __init__(self, result_cd: str, detail: str, api: str) -> None:
        self.result_cd = str(result_cd)
        self.detail = str(detail)
        self.api = api
        super().__init__(f'{api}: {result_cd} {detail}')


class AddressRefineError(CJApiError):
    """주소 정제 업무 오류."""


class DuplicateBookingError(CJApiError):
    """기존 예약과 충돌한 접수 요청."""


class CJAuthError(CJApiError):
    """토큰 인증 실패."""


class CJNetworkError(Exception):
    """재시도 후에도 해결되지 않은 전송 오류."""


class CJClient:
    """토큰 캐시와 재시도를 갖춘 CJ API 클라이언트."""

    def __init__(
        self,
        config: Config,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] | None = None,
        retry_base: float = 0.2,
    ) -> None:
        self.config = config
        self.sleep = sleep
        self.clock = clock
        self.now = now or dt.datetime.now
        self.retry_base = retry_base
        self.token: str | None = None
        self.expiry: dt.datetime | None = None
        self.last_issue: float | None = None
        self.lock = threading.RLock()
        self.log = logging.getLogger('cj_toy')

    def _request(self, api: str, data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['CJ-Gateway-APIKey'] = token
        body = json.dumps({'DATA': data}, ensure_ascii=False).encode('utf-8')
        for attempt in range(self.config.max_retries + 1):
            if api == TOKEN_API:
                if self.last_issue is not None:
                    wait = 1.1 - (self.clock() - self.last_issue)
                    if wait > 0:
                        self.sleep(wait)
                self.last_issue = self.clock()
            start = self.clock()
            status = 200
            try:
                request = urllib.request.Request(
                    self.config.base_url + '/' + api,
                    data=body,
                    headers=headers,
                    method='POST',
                )
                try:
                    with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                        raw = response.read()
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    raw = exc.read()
                if api == TOKEN_API:
                    self.last_issue = self.clock()
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    payload = {'RESULT_CD': f'E{status}', 'RESULT_DETAIL': 'Invalid JSON response'}
                self.log.info(
                    'api_response',
                    extra={'fields': {
                        'api': api,
                        'attempt': attempt + 1,
                        'elapsed_ms': round((self.clock() - start) * 1000),
                        'result_cd': payload.get('RESULT_CD'),
                        'request': data,
                        'response': payload,
                    }},
                )
                if (status == 429 or status >= 500) and attempt < self.config.max_retries:
                    self._backoff(api, attempt, f'HTTP {status}')
                    continue
                code = str(payload.get('RESULT_CD', ''))
                if status >= 400 or code not in (RESULT_SUCCESS, RESULT_GATEWAY_SUCCESS):
                    error_class: type[CJApiError] = CJApiError
                    if status == 401 or code == AUTH_ERROR:
                        error_class = CJAuthError
                    elif api == ADDRESS_API and code in ADDRESS_ERRORS:
                        error_class = AddressRefineError
                    elif (api == BOOK_API
                          and DUPLICATE_DETAIL in str(payload.get('RESULT_DETAIL', ''))):
                        error_class = DuplicateBookingError
                    raise error_class(code or f'E{status}', payload.get('RESULT_DETAIL', ''), api)
                return payload
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if api == TOKEN_API:
                    self.last_issue = self.clock()
                if attempt == self.config.max_retries:
                    raise CJNetworkError(f'{api}: network failure: {type(exc).__name__}') from exc
                self._backoff(api, attempt, type(exc).__name__)
        raise AssertionError('unreachable')

    def _backoff(self, api: str, attempt: int, reason: str) -> None:
        self.log.info(
            'api_retry',
            extra={'fields': {'api': api, 'attempt': attempt + 1, 'reason': reason}},
        )
        self.sleep(self.retry_base * 2 ** attempt + random.uniform(0, self.retry_base / 10))

    def _token(self) -> str:
        with self.lock:
            if self.token and self.expiry and (self.expiry - self.now()).total_seconds() >= 1800:
                return self.token
            data = self._request(TOKEN_API, {
                'CUST_ID': self.config.cust_id,
                'BIZ_REG_NUM': self.config.biz_reg_num,
            })['DATA']
            self.token = data['TOKEN_NUM']
            self.expiry = dt.datetime.strptime(data['TOKEN_EXPRTN_DTM'], '%Y%m%d%H%M%S')
            return self.token

    def _call(self, api: str, data: dict[str, Any]) -> dict[str, Any]:
        token = self._token()
        for auth_attempt in range(2):
            try:
                return self._request(api, {**data, 'TOKEN_NUM': token}, token)
            except CJAuthError:
                if auth_attempt:
                    raise
                with self.lock:
                    if self.token == token:
                        self.token = None
                        self.expiry = None
                        self.sleep(self.config.auth_retry_wait)
                    token = self._token()
        raise AssertionError('unreachable')

    def issue_token(self) -> str:
        """유효한 토큰을 반환하고 필요한 경우 발급한다."""
        return self._token()

    def refine_address(self, address: str, clntnum: str | None = None) -> dict[str, Any]:
        """받는 주소의 분류 정보를 조회한다."""
        if not address or len(address) > 100:
            raise ValueError('ADDRESS는 1~100자여야 합니다')
        customer = clntnum or self.config.cust_id
        return self._call(ADDRESS_API, {
            'CLNTNUM': customer,
            'CLNTMGMCUSTCD': customer,
            'ADDRESS': address,
        })['DATA']

    def request_invoice(self) -> str:
        """운송장 번호 한 개를 채번한다."""
        return self._call(INVOICE_API, {'CLNTNUM': self.config.cust_id})['DATA']['INVC_NO']

    def register_booking(self, booking: dict[str, Any]) -> dict[str, Any]:
        """예약 접수를 요청한다."""
        return self._call(BOOK_API, booking)

    def cancel_booking(self, booking: dict[str, Any]) -> dict[str, Any]:
        """기존 접수 필드로 예약 취소를 요청한다."""
        return self._call(CANCEL_API, {**booking, 'REQ_DV_CD': '02'})

    def track(self, invc_no: str) -> list[dict[str, Any]]:
        """운송장 번호로 배송 이벤트를 조회한다."""
        return self._call(TRACK_API, {'CLNTNUM': self.config.cust_id, 'INVC_NO': invc_no})['DATA']
