"""구조화 로그와 민감정보 마스킹. 가이드 V3.9.4 1.3.2~1.3.7."""

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any

_PHONE = re.compile(r'(?<!\d)(\d{2,3})[- ]?(\d{3,4})[- ]?(\d{4})(?!\d)')


def mask(value: Any, key: str = '') -> Any:
    """사전과 목록을 재귀적으로 순회하며 개인 정보와 토큰을 가린다."""
    key = key.upper()
    if isinstance(value, dict):
        return {child_key: mask(child, child_key) for child_key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(child, key) for child in value]
    if not isinstance(value, str):
        return value
    if key in ('TOKEN_NUM', 'CJ-GATEWAY-APIKEY'):
        return value[:4] + '***'
    if key == 'BIZ_REG_NUM':
        return '******' + value[-4:]
    if re.search(r'(TEL|CELL|SAFE)_NO[123]$', key):
        return '****' if key.endswith('2') else value
    if 'TEL' in key or 'PHONE' in key:
        return _PHONE.sub(lambda match: match[1] + '-****-' + match[3], value)
    person_name = key.endswith('NM') and any(
        part in key for part in ('SENDR', 'RCVR', 'ORDRR', 'EMP', 'ACPTR')
    )
    if person_name or key in ('NAME', 'SENDER_NAME', 'RECEIVER_NAME'):
        if len(value) <= 2:
            return value[:1] + '*'
        return value[:1] + '*' * (len(value) - 2) + value[-1:]
    if 'ADDR' in key or key == 'ADDRESS':
        match = re.search(r'.*(?:시|구|군)', value)
        return (match.group(0) if match else '') + '***'
    return _PHONE.sub(lambda match: match[1] + '-****-' + match[3], value)


class JsonFormatter(logging.Formatter):
    """레코드를 마스킹된 JSON 한 줄로 변환한다."""

    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드와 부가 필드를 직렬화한다."""
        data = {
            'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'level': record.levelname,
            'event': record.getMessage(),
        }
        data.update(getattr(record, 'fields', {}))
        return json.dumps(mask(data), ensure_ascii=False, default=str)


def configure(path: str | Path | None = None, *, stderr: bool = False) -> logging.Logger:
    """파일 또는 표준 오류에 마스킹된 로그를 설정한다."""
    logger = logging.getLogger('cj_toy')
    logger.handlers.clear()
    if path:
        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    if stderr or not path:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
