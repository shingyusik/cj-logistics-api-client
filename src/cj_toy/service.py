"""정제·채번·접수와 로컬 멱등성. 가이드 V3.9.4 1.3.4, 1.3.6~1.3.7, 1.3.10."""

import datetime
import json
import os
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .client import CJClient, DuplicateBookingError
from .label import build_label, export_labels
from .models import BookingResult, Shipment, split_phone


class ShipmentService:
    """배송 요청과 단일 프로세스용 JSON 저장소를 관리한다."""

    def __init__(
        self,
        client: CJClient,
        store_path: str | Path = 'out/bookings.json',
        output_dir: str | Path = 'out',
    ) -> None:
        self.client = client
        self.path = Path(store_path)
        self.output_dir = Path(output_dir)
        self.lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix='.bookings-')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def create_shipment(self, shipment: Shipment) -> BookingResult:
        """성공 기록이 없으면 주소 정제, 채번, 접수를 수행한다."""
        shipment.validate()
        with self.lock:
            store = self._load()
            existing = store.get(shipment.cust_use_no)
            if existing and not existing.get('cancelled'):
                return BookingResult(**existing['result'])
            date = datetime.datetime.now().strftime('%Y%m%d')
            customer = self.client.config.cust_id
            key = f'{date}_{customer}_{shipment.cust_use_no}'
            if len(key) > 100:
                raise ValueError('합포장 키 길이 오류')
            refined = self.client.refine_address(shipment.receiver.address)
            invoice = self.client.request_invoice()
            booking = self._booking(shipment, customer, date, key, invoice)
            try:
                self.client.register_booking(booking)
            except DuplicateBookingError:
                fresh = self._load().get(shipment.cust_use_no)
                if fresh and not fresh.get('cancelled'):
                    return BookingResult(**fresh['result'])
                raise
            result = BookingResult(
                shipment.cust_use_no, invoice, build_label(shipment, invoice, refined),
            )
            store[shipment.cust_use_no] = {
                'result': asdict(result), 'booking': booking, 'cancelled': False,
            }
            self._save(store)
            self._export(store)
            return result

    @staticmethod
    def _booking(
        shipment: Shipment, customer: str, date: str, key: str, invoice: str,
    ) -> dict[str, Any]:
        booking = {
            'CUST_ID': customer,
            'RCPT_YMD': date,
            'CUST_USE_NO': shipment.cust_use_no,
            'RCPT_DV': '01',
            'WORK_DV_CD': '01',
            'REQ_DV_CD': '01',
            'MPCK_KEY': key,
            'CAL_DV_CD': '01',
            'FRT_DV_CD': '01',
            'CNTR_ITEM_CD': '01',
            'BOX_TYPE_CD': shipment.box_type,
            'BOX_QTY': 1,
            'CUST_MGMT_DLCM_CD': customer,
            'INVC_NO': invoice,
            'PRT_ST': '02',
            'DLV_DV': '01',
            'REMARK_1': shipment.remark,
            'ARRAY': [
                {'MPCK_SEQ': number, 'GDS_NM': item.name, 'GDS_QTY': item.quantity}
                for number, item in enumerate(shipment.items, 1)
            ],
        }
        for prefix, party in (('SENDR', shipment.sender), ('RCVR', shipment.receiver)):
            booking.update({
                prefix + '_NM': party.name,
                prefix + '_ZIP_NO': party.zip_code,
                prefix + '_ADDR': party.address,
                prefix + '_DETAIL_ADDR': party.detail_address,
            })
            for number, part in enumerate(split_phone(party.phone), 1):
                booking[f'{prefix}_TEL_NO{number}'] = part
        return booking

    def _export(self, store: dict[str, Any]) -> None:
        labels = [
            entry['result']['label'] for entry in store.values() if not entry.get('cancelled')
        ]
        export_labels(labels, self.output_dir)

    def cancel_shipment(self, cust_use_no: str) -> None:
        """저장된 접수 정보로 예약을 취소한다."""
        with self.lock:
            store = self._load()
            entry = store.get(cust_use_no)
            if not entry or entry.get('cancelled'):
                raise ValueError('취소할 로컬 예약이 없습니다')
            self.client.cancel_booking(entry['booking'])
            entry['cancelled'] = True
            self._save(store)
            self._export(store)

    def track(self, invc_no: str) -> list[dict[str, Any]]:
        """운송장별 이벤트를 조회한다."""
        return self.client.track(invc_no)
