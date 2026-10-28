"""테스트. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""
from typing import Any
import io
import json
import pytest
from cj_toy.config import Config
from cj_toy.logging_utils import mask
from cj_toy.models import split_phone
from cj_toy.cli import sample
from cj_toy.public_tracking import track


@pytest.mark.parametrize('value,expected', [('홍길동', '홍*동'), ('김철수', '김*수'), ('홍길', '홍*')])
def test_name_mask(value: str, expected: str) -> None:
    """test name mask 동작을 확인한다."""
    assert mask(value, 'RCVR_NM') == expected


def test_nested_mask() -> None:
    """test nested mask 동작을 확인한다."""
    data = mask({'DATA': {
        'TOKEN_NUM': 'abcdef', 'BIZ_REG_NUM': '0000001234',
        'RCVR_TEL_NO1': '010', 'RCVR_TEL_NO2': '0000', 'RCVR_TEL_NO3': '1234',
        'RCVR_ADDR': '서울특별시 중구 세종대로 110',
        'DEALT_EMP_TEL': '010-0000-1234', 'RCVR_NM': '김철수',
    }})['DATA']
    assert data['TOKEN_NUM'] == 'abcd***' and data['BIZ_REG_NUM'] == '******1234'
    assert data['RCVR_TEL_NO2'] == '****' and data['DEALT_EMP_TEL'] == '010-****-1234'
    assert data['RCVR_ADDR'] == '서울특별시 중구***' and data['RCVR_NM'] == '김*수'


def test_header_mask() -> None:
    """test header mask 동작을 확인한다."""
    assert mask('abcdef', 'CJ-Gateway-APIKey') == 'abcd***'


def test_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """test config env 동작을 확인한다."""
    monkeypatch.setenv('CJ_CUST_ID', 'TEST')
    monkeypatch.setenv('CJ_BIZ_REG_NUM', '0000000000')
    monkeypatch.setenv('CJ_AUTH_RETRY_WAIT', '2')
    c = Config.from_env()
    assert c.cust_id == 'TEST' and c.auth_retry_wait == 2


def test_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """test config missing 동작을 확인한다."""
    monkeypatch.delenv('CJ_CUST_ID', raising=False)
    monkeypatch.delenv('CJ_BIZ_REG_NUM', raising=False)
    with pytest.raises(ValueError):
        Config.from_env()


@pytest.mark.parametrize('biz', ['000', '000000000a', '００００００００００'])
def test_config_invalid_biz(biz: str) -> None:
    """test config invalid biz 동작을 확인한다."""
    with pytest.raises(ValueError):
        Config('TEST', biz)


@pytest.mark.parametrize('phone', ['010-0000-0000', '02-0000-0000'])
def test_phone_valid(phone: str) -> None:
    """test phone valid 동작을 확인한다."""
    assert len(split_phone(phone)) == 3


@pytest.mark.parametrize('phone', ['01000000000', '010-00000-0000', '010-abc-0000', '010--0000'])
def test_phone_invalid(phone: str) -> None:
    """test phone invalid 동작을 확인한다."""
    with pytest.raises(ValueError):
        split_phone(phone)


@pytest.mark.parametrize(
    'field,value', [
        ('address', '가' * 101), ('detail_address', '가' * 301),
        ('zip_code', '1234'), ('name', '가' * 101),
    ],
)
def test_field_lengths(field: str, value: str) -> None:
    """test field lengths 동작을 확인한다."""
    s = sample()
    setattr(s.receiver, field, value)
    with pytest.raises(ValueError):
        s.validate()


def test_public_parser() -> None:
    """test public parser 동작을 확인한다."""

    class Response(io.BytesIO):
        """Response 테스트 보조 객체."""
        pass

    class Opener:
        """Opener 테스트 보조 객체."""

        def __init__(self) -> Any:
            """테스트 요청을 기록한다."""
            self.requests = []

        def open(self, req: Any, timeout: Any) -> Any:
            """open 동작을 확인한다."""
            self.requests.append(req)
            if len(self.requests) == 1:
                return Response(b'<input value="secret" name="_csrf">')
            event = {
                'dTime': 'now', 'regBranNm': 'branch', 'crgSt': '91',
                'scanNm': 'done', 'crgNm': 'PRIVATE',
            }
            return Response(json.dumps({'parcelDetailResultMap': {'resultList': [event]}}).encode())
    opener = Opener()
    result = track('000000000000', opener)
    assert result == [{'dTime': 'now', 'regBranNm': 'branch', 'crgSt': '91', 'scanNm': 'done'}]
    assert b'_csrf=secret' in opener.requests[1].data and 'crgNm' not in result[0]


def test_public_missing_csrf() -> None:
    """test public missing csrf 동작을 확인한다."""

    class Opener:
        """Opener 테스트 보조 객체."""

        def open(self, *args: Any, **kwargs: Any) -> Any:
            """open 동작을 확인한다."""
            return io.BytesIO(b'<html>none</html>')
    with pytest.raises(ValueError):
        track('000000000000', Opener())


def test_public_status_reporting() -> None:
    """공개 조회 상태를 알리고 토큰 값은 보고하지 않는다."""
    class Response(io.BytesIO):
        """HTTP 상태를 가진 메모리 응답."""
        status = 200

    class Opener:
        """두 단계 응답을 순서대로 제공한다."""

        def __init__(self) -> None:
            self.calls = 0

        def open(self, request: Any, timeout: int) -> Response:
            """공개 페이지 또는 빈 배송 이벤트를 반환한다."""
            self.calls += 1
            if self.calls == 1:
                return Response(b'<input name="_csrf" value="secret-token">')
            return Response(b'{"parcelDetailResultMap": {"resultList": []}}')

    reported: dict[str, Any] = {}
    result = track('000000000000', Opener(), lambda key, value: reported.update({key: value}))
    assert result == []
    assert reported == {'get_status': 200, 'csrf_acquired': True, 'post_status': 200}
    assert 'secret-token' not in str(reported)
