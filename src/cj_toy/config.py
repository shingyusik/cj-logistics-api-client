"""환경변수 설정. 가이드 V3.9.4 1.3.2~1.3.3."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """CJ 접속 정보와 재시도 정책."""

    cust_id: str
    biz_reg_num: str
    base_url: str = 'http://127.0.0.1:8765'
    timeout: float = 5.0
    max_retries: int = 2
    auth_retry_wait: float = 60.0

    def __post_init__(self) -> None:
        if not self.cust_id or len(self.cust_id) > 20:
            raise ValueError('CJ_CUST_ID는 1~20자여야 합니다')
        if (len(self.biz_reg_num) != 10 or not self.biz_reg_num.isascii()
                or not self.biz_reg_num.isdigit()):
            raise ValueError('CJ_BIZ_REG_NUM은 숫자 10자리여야 합니다')
        if self.timeout <= 0 or self.max_retries < 0 or self.auth_retry_wait < 0:
            raise ValueError('시간과 재시도 설정이 올바르지 않습니다')

    @classmethod
    def from_env(cls) -> 'Config':
        """프로세스 환경변수에서 설정을 읽는다."""
        return cls(
            os.getenv('CJ_CUST_ID', ''),
            os.getenv('CJ_BIZ_REG_NUM', ''),
            os.getenv('CJ_BASE_URL', 'http://127.0.0.1:8765').rstrip('/'),
            float(os.getenv('CJ_TIMEOUT', '5')),
            int(os.getenv('CJ_MAX_RETRIES', '2')),
            float(os.getenv('CJ_AUTH_RETRY_WAIT', '60')),
        )
