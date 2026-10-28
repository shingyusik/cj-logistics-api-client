"""비공식 웹 조회. 가이드 V3.9.4 1.3.5 계약 API와는 별도 기능이다."""

import http.cookiejar
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

PUBLIC_BASE = 'https://www.cjlogistics.com/ko/tool/parcel/'
PUBLIC_FIELDS = ('dTime', 'regBranNm', 'crgSt', 'scanNm')


class CsrfParser(HTMLParser):
    """공개 페이지의 CSRF 입력값을 추출한다."""

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """입력 태그에서 토큰 필드를 찾는다."""
        attributes = dict(attrs)
        if tag.lower() == 'input' and attributes.get('name') == '_csrf':
            self.token = attributes.get('value')


def track(
    invoice: str,
    opener: Any = None,
    report: Callable[[str, Any], None] | None = None,
) -> list[dict[str, Any]]:
    """쿠키와 CSRF를 이용해 공개 웹 조회 후 직원 정보를 제거한다."""
    if len(invoice) != 12 or not invoice.isascii() or not invoice.isdigit():
        raise ValueError('운송장 번호는 숫자 12자리여야 합니다')
    opener = opener or urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    with opener.open(PUBLIC_BASE + 'tracking', timeout=10) as response:
        page = response.read().decode('utf-8')
        if report:
            report('get_status', getattr(response, 'status', None))
    parser = CsrfParser()
    parser.feed(page)
    if report:
        report('csrf_acquired', bool(parser.token))
    if not parser.token:
        raise ValueError('공개 페이지에서 CSRF 토큰을 찾지 못했습니다')
    data = urllib.parse.urlencode({'_csrf': parser.token, 'paramInvcNo': invoice}).encode()
    request = urllib.request.Request(PUBLIC_BASE + 'tracking-detail', data=data, method='POST')
    with opener.open(request, timeout=10) as response:
        payload = json.load(response)
        if report:
            report('post_status', getattr(response, 'status', None))
    items = (payload.get('parcelDetailResultMap') or {}).get('resultList', []) or []
    return [{key: item.get(key) for key in PUBLIC_FIELDS} for item in items]
