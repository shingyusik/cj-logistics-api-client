"""API 경로와 결과 코드. 가이드 V3.9.4 1.3.2~1.3.7, 1.3.10."""

TOKEN_API = 'ReqOneDayToken'
ADDRESS_API = 'ReqAddrRfnSm'
INVOICE_API = 'ReqInvcNo'
BOOK_API = 'RegBook'
CANCEL_API = 'CnclBook'
TRACK_API = 'ReqOneGdsTrc'
API_PATHS = (TOKEN_API, ADDRESS_API, INVOICE_API, BOOK_API, CANCEL_API, TRACK_API)
RESULT_SUCCESS = 'S'
RESULT_GATEWAY_SUCCESS = 'S200'
RESULT_ERROR = 'E'
AUTH_ERROR = 'E401'
DUPLICATE_DETAIL = 'ORA-00001'
ADDRESS_ERRORS = {
    '-20000': '입력 코드 오류',
    '-20001': '등록되지 않은 고객 ID',
    '-20002': '주소 분석 실패',
    '-20003': '집배권역 설정 없음',
    '-20004': '폐점 또는 사용 중지된 점소',
    '-20005': '담당 사원 미설정',
    '-20006': '도착지 코드 추출 실패',
    '-20007': '분류주소 추출 실패',
    '-20008': '계약 없음 또는 만료',
    '-20009': '배송 불가 지역',
    '-20010': '배송 지연 가능 지역',
}
