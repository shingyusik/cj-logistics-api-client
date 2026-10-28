"""인쇄 데이터와 가정 기반 미리보기. 가이드 V3.9.4 1.3.4, 1.3.15."""

import csv
import html
import json
from pathlib import Path
from typing import Any

from .models import Shipment

NOTE = '레이아웃 가정 (CJ 표준 운송장 가이드 미확인)'
SORT_FIELDS = (
    'CLSFCD', 'SUBCLSFCD', 'CLSFADDR', 'CLLDLVBRANNM', 'CLLDLVEMPNICKNM', 'P2PCD', 'RSPSDIV',
)


def build_label(shipment: Shipment, invc_no: str, refined: dict[str, Any]) -> dict[str, Any]:
    """정제 결과와 접수 정보를 인쇄용 데이터로 조합한다."""
    # ASSUMPTION: preview layout is not an approved CJ label or barcode.
    label = {
        'layout_assumption': True,
        'layout_note': NOTE,
        'INVC_NO': invc_no,
        'formatted_invoice': f'{invc_no[:4]}-{invc_no[4:8]}-{invc_no[8:]}',
        **{key: refined[key] for key in SORT_FIELDS},
    }
    for prefix, party in (('sender', shipment.sender), ('receiver', shipment.receiver)):
        label.update({
            f'{prefix}_name': party.name,
            f'{prefix}_phone': party.phone,
            f'{prefix}_zip': party.zip_code,
            f'{prefix}_address': party.address,
            f'{prefix}_detail_address': party.detail_address,
        })
    label.update({
        'goods_summary': ', '.join(f'{item.name} x {item.quantity}' for item in shipment.items),
        'BOX_TYPE_CD': shipment.box_type,
        'REMARK_1': shipment.remark,
    })
    return label


def export_labels(labels: list[dict[str, Any]], directory: str | Path = 'out') -> None:
    """JSON, 평탄화 CSV와 HTML 미리보기를 저장한다."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / 'labels.json').write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding='utf-8',
    )
    keys = list(labels[0]) if labels else ['layout_assumption', 'layout_note']
    with (path / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(labels)
    for label in labels:
        invoice = label['INVC_NO']
        if not invoice.isascii() or not invoice.isdigit() or len(invoice) != 12:
            raise ValueError('운송장 번호 오류')
        rows = ''.join(
            f'<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>'
            for key, value in label.items()
        )
        document = (
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            f'<title>라벨 미리보기</title><h1>{NOTE}</h1><table>{rows}</table></html>'
        )
        (path / f'label_{invoice}.html').write_text(document, encoding='utf-8')
