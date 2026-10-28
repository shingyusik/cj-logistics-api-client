"""테스트. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""
from collections.abc import Iterator
import sys
import threading
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cj_toy.client import CJClient
from cj_toy.config import Config
from cj_toy.mock_server import MockServer
from cj_toy.service import ShipmentService


@pytest.fixture
def server() -> Iterator[MockServer]:
    """server 동작을 확인한다."""
    s = MockServer(('127.0.0.1', 0), 'MOCK', '0000000000')
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield s
    s.shutdown()
    s.server_close()
    thread.join()


@pytest.fixture
def client(server: MockServer) -> CJClient:
    """client 동작을 확인한다."""
    config = Config(
        'MOCK', '0000000000', f'http://127.0.0.1:{server.server_port}',
        timeout=0.05, max_retries=2, auth_retry_wait=0,
    )
    return CJClient(config, retry_base=0.001)


@pytest.fixture
def service(client: CJClient, tmp_path: Path) -> ShipmentService:
    """service 동작을 확인한다."""
    return ShipmentService(client, tmp_path / 'bookings.json', tmp_path / 'labels')
