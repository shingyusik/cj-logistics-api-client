"""접수 입력과 검증. 가이드 V3.9.4 1.3.4, 1.3.7."""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Party:
    """송하인 또는 수하인의 인쇄 정보."""

    name: str
    phone: str
    zip_code: str
    address: str
    detail_address: str

    def validate(self) -> None:
        """접수 필드 크기와 필수값을 확인한다."""
        if not self.name or len(self.name) > 100:
            raise ValueError('이름 길이 오류')
        split_phone(self.phone)
        if not re.fullmatch(r'\d{5,6}', self.zip_code):
            raise ValueError('우편번호는 숫자 5~6자리여야 합니다')
        if not self.address or len(self.address) > 150:
            raise ValueError('주소 길이 오류')
        if not self.detail_address or len(self.detail_address) > 300:
            raise ValueError('상세주소 길이 오류')


def split_phone(phone: str) -> list[str]:
    """하이픈으로 구분된 전화번호를 세 필드로 나눈다."""
    parts = phone.split('-')
    if len(parts) != 3 or any(
        not part.isascii() or not part.isdigit() or len(part) > 4 for part in parts
    ):
        raise ValueError('전화번호는 각 4자리 이하의 숫자 3부분이어야 합니다')
    return parts


@dataclass
class Item:
    """접수할 상품과 수량."""

    name: str
    quantity: int = 1


@dataclass
class Shipment:
    """고객사용번호를 가진 배송 요청."""

    cust_use_no: str
    sender: Party
    receiver: Party
    items: list[Item]
    box_type: str = '02'
    remark: str = ''

    def validate(self) -> None:
        """주소 정제와 접수에 필요한 입력을 검증한다."""
        if not self.cust_use_no or len(self.cust_use_no) > 50:
            raise ValueError('고객사용번호 길이 오류')
        self.sender.validate()
        self.receiver.validate()
        if len(self.receiver.address) > 100:
            raise ValueError('ADDRESS는 100자 이하여야 합니다')
        if not self.items or any(
            not item.name or len(item.name) > 500 or item.quantity < 1 for item in self.items
        ):
            raise ValueError('상품 오류')
        if self.box_type not in ('01', '02', '03', '04', '05', '06', '07'):
            raise ValueError('박스 오류')
        if len(self.remark) > 1000:
            raise ValueError('비고 오류')


@dataclass
class RefinedAddress:
    """주소 정제 API가 제공하는 분류 정보."""

    CLSFCD: str
    SUBCLSFCD: str
    CLSFADDR: str
    CLLDLVBRANNM: str
    CLLDLVEMPNM: str
    CLLDLVEMPNICKNM: str
    RSPSDIV: str
    P2PCD: str


@dataclass
class BookingResult:
    """로컬에 보관하는 예약 결과."""

    cust_use_no: str
    invc_no: str
    label: dict[str, Any] = field(default_factory=dict)
