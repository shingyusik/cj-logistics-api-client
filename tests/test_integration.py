"""테스트. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""
from pathlib import Path
import csv
import datetime as dt
import json
import pytest
from cj_toy.cli import sample
from cj_toy.client import AddressRefineError, CJApiError, CJNetworkError, DuplicateBookingError
from cj_toy.service import ShipmentService
from cj_toy.client import CJClient
from cj_toy.mock_server import MockServer


def test_end_to_end(service: ShipmentService, server: MockServer) -> None:
    """test end to end 동작을 확인한다."""
    result = service.create_shipment(sample())
    assert result.invc_no == '650000000001'
    data = next(iter(server.bookings.values()))['data']
    assert data['PRT_ST'] == '02' and data['INVC_NO'] == result.invc_no
    assert data['SENDR_TEL_NO2'] == '0000'
    assert data['MPCK_KEY'].endswith('_MOCK_SAMPLE-001')


def test_label_files(service: ShipmentService, tmp_path: Path) -> None:
    """test label files 동작을 확인한다."""
    r = service.create_shipment(sample())
    folder = tmp_path / 'labels'
    label = json.loads((folder / 'labels.json').read_text())[0]
    assert label['layout_assumption'] is True
    assert label['CLSFCD'] and label['SUBCLSFCD'] and label['P2PCD']
    with (folder / 'labels.csv').open(encoding='utf-8-sig') as f:
        row = next(csv.DictReader(f))
    assert row['CLSFCD'] == label['CLSFCD'] and row['layout_assumption'] == 'True'
    assert '레이아웃 가정' in (folder / f'label_{r.invc_no}.html').read_text()


@pytest.mark.parametrize(
    'address,code', [('분석불가', '-20002'), ('권역없음', '-20003'), ('배송불가', '-20009')],
)
def test_address_failure_before_number(
    service: ShipmentService, server: MockServer, address: str, code: str,
) -> None:
    """test address failure before number 동작을 확인한다."""
    with pytest.raises(AddressRefineError) as e:
        service.create_shipment(sample(address=address))
    assert e.value.result_cd == code and server.calls.get('ReqInvcNo', 0) == 0


def test_customer_error(client: CJClient) -> None:
    """test customer error 동작을 확인한다."""
    with pytest.raises(AddressRefineError) as e:
        client.refine_address('서울특별시', clntnum='WRONG')
    assert e.value.result_cd == '-20001'


@pytest.mark.parametrize('fault', ['500', '429', 'delay'])
def test_retry_success(client: CJClient, server: MockServer, fault: str) -> None:
    """test retry success 동작을 확인한다."""
    server.delay_seconds = 0.08
    server.fail_next('ReqInvcNo', fault)
    assert client.request_invoice() == '650000000001'
    assert server.calls['ReqInvcNo'] == 2


def test_timeout_exhaustion(client: CJClient, server: MockServer) -> None:
    """test timeout exhaustion 동작을 확인한다."""
    server.delay_seconds = 0.1
    server.fail_next('ReqInvcNo', 'delay', 3)
    with pytest.raises(CJNetworkError):
        client.request_invoice()
    assert server.calls['ReqInvcNo'] == 3


def test_no_retry_400(client: CJClient, server: MockServer) -> None:
    """test no retry 400 동작을 확인한다."""
    with pytest.raises(CJApiError) as e:
        client._call('ReqInvcNo', {})
    assert e.value.result_cd == 'E400' and server.calls['ReqInvcNo'] == 1


def test_token_cached(client: CJClient, server: MockServer) -> None:
    """test token cached 동작을 확인한다."""
    for _ in range(4):
        client.refine_address('서울특별시 중구')
    assert server.calls['ReqOneDayToken'] == 1


def test_refresh_near_expiry(client: CJClient, server: MockServer) -> None:
    """test refresh near expiry 동작을 확인한다."""
    client.issue_token()
    client.expiry = dt.datetime.now() + dt.timedelta(minutes=29)
    client.issue_token()
    assert server.calls['ReqOneDayToken'] == 2


def test_auth_reissue(client: CJClient, server: MockServer) -> None:
    """test auth reissue 동작을 확인한다."""
    old = client.issue_token()
    server.expire_token()
    client.refine_address('서울특별시 중구')
    assert client.token != old and server.calls['ReqOneDayToken'] == 2


def test_issue_throttle(client: CJClient, server: MockServer) -> None:
    """test issue throttle 동작을 확인한다."""
    client.issue_token()
    client.token = None
    start = client.clock()
    client.issue_token()
    assert client.clock() - start >= 0.95 and server.calls['ReqOneDayToken'] == 2


def test_idempotency(service: ShipmentService, server: MockServer) -> None:
    """test idempotency 동작을 확인한다."""
    a = service.create_shipment(sample())
    calls = dict(server.calls)
    b = service.create_shipment(sample())
    assert a == b and calls == server.calls


def test_remote_duplicate(service: ShipmentService, client: CJClient, tmp_path: Path) -> None:
    """test remote duplicate 동작을 확인한다."""
    service.create_shipment(sample())
    with pytest.raises(DuplicateBookingError):
        other = ShipmentService(client, tmp_path / 'different.json', tmp_path / 'different')
        other.create_shipment(sample())


def test_cancel(service: ShipmentService, server: MockServer) -> None:
    """test cancel 동작을 확인한다."""
    service.create_shipment(sample())
    service.cancel_shipment('SAMPLE-001')
    assert next(iter(server.bookings.values()))['cancelled']


def test_cancel_not_found(service: ShipmentService) -> None:
    """test cancel not found 동작을 확인한다."""
    with pytest.raises(ValueError):
        service.cancel_shipment('MISSING')


def test_cancel_remote_not_found(service: ShipmentService, client: CJClient) -> None:
    """test cancel remote not found 동작을 확인한다."""
    service.create_shipment(sample())
    booking = service._load()['SAMPLE-001']['booking']
    booking['CUST_USE_NO'] = 'MISSING'
    with pytest.raises(CJApiError):
        client.cancel_booking(booking)


def test_tracking(service: ShipmentService) -> None:
    """test tracking 동작을 확인한다."""
    r = service.create_shipment(sample())
    events = service.track(r.invc_no)
    assert [x['CRG_ST'] for x in events] == ['11', '41', '82', '91']
    with pytest.raises(CJApiError):
        service.cancel_shipment('SAMPLE-001')


def test_tracking_unknown(client: CJClient) -> None:
    """test tracking unknown 동작을 확인한다."""
    with pytest.raises(CJApiError) as e:
        client.track('000000000000')
    assert e.value.result_cd == 'E404'


def test_token_retry_throttled(client: CJClient, server: MockServer) -> None:
    """test token retry throttled 동작을 확인한다."""
    server.fail_next('ReqOneDayToken', '500')
    start = client.clock()
    client.issue_token()
    assert client.clock() - start >= 0.95 and server.calls['ReqOneDayToken'] == 2


def test_label_csv_flat_columns(service: ShipmentService, tmp_path: Path) -> None:
    """CSV는 송하인과 수하인을 개별 열로 기록한다."""
    service.create_shipment(sample())
    with (tmp_path / 'labels' / 'labels.csv').open(encoding='utf-8-sig') as file:
        row = next(csv.DictReader(file))
    assert row['sender_name'] == '홍길동'
    assert row['sender_phone'] == '010-0000-0000'
    assert row['receiver_name'] == '김철수'
    assert row['receiver_zip'] == '04524'
    assert row['receiver_address'] and row['receiver_detail_address']
    assert 'sender' not in row and 'receiver' not in row
