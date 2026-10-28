# cj-logistics-api-client

Python client + spec-based mock server for the CJ Logistics parcel standard API (V3.9.4). Toy project.

CJ대한통운 택배 표준 API V3.9.4 규격에 따라 주소 정제부터 송장 출력 데이터까지 연결하고 로컬 mock으로 검증한 Python 토이 프로젝트입니다.

## 무엇을 하는가

받는 사람 주소를 먼저 정제하고 운송장 번호를 채번한 뒤 예약을 접수합니다. 성공한 고객사용번호는 로컬 JSON에 저장하여 재요청 시 같은 결과를 돌려줍니다. 예약 취소, 운송장 추적, JSON·CSV 출력 데이터와 HTML 미리보기도 제공합니다. 주소 정제에 실패하면 채번 전에 중단합니다.

```text
CLI → ShipmentService → CJClient (토큰 관리, 재시도) → CJ API (mock | dev)
              ├→ 라벨 출력 (JSON / CSV / HTML)
              └→ 로컬 멱등 저장소
             구조화 로그 / 마스킹
```

| 경로 | 용도 | 주요 필드 |
| --- | --- | --- |
| `/ReqOneDayToken` | 1일 토큰 발급 | CUST_ID, BIZ_REG_NUM, TOKEN_NUM, TOKEN_EXPRTN_DTM |
| `/ReqAddrRfnSm` | 주소 정제 | CLNTNUM, CLNTMGMCUSTCD, ADDRESS, CLSFCD, SUBCLSFCD |
| `/ReqInvcNo` | 운송장 채번 | CLNTNUM, INVC_NO |
| `/RegBook` | 예약 접수 | CUST_USE_NO, MPCK_KEY, INVC_NO, PRT_ST, ARRAY |
| `/CnclBook` | 예약 취소 | 접수 필드, REQ_DV_CD |
| `/ReqOneGdsTrc` | 운송장 추적 | CLNTNUM, INVC_NO, CRG_ST |

## 파일 구성

- `src/cj_toy/client.py`, `constants.py`: CJ 요청, 토큰 관리, 재시도와 API·오류 코드.
- `service.py`, `models.py`, `label.py`: 입력 검증, 접수·멱등성, 평탄화 CSV와 JSON·HTML 출력.
- `mock_server.py`, `logging_utils.py`: 로컬 API 시뮬레이션과 마스킹된 구조화 로그.
- `cli.py`, `public_tracking.py`: 데모·명령행과 선택적인 공개 웹 조회.
- `tests/`: mock 통합 테스트와 단위 테스트. `docs/`: 실제 실행 기록.

## 실제 호출과 mock

| 대상 | 검증 범위 |
| --- | --- |
| CJ dxapi 6개 API | 전부 로컬 mock 서버로만 검증, 실서버 호출 0회 (계약 고객ID 없음) |
| 공개 배송조회 웹페이지 | GET(+가짜 번호 POST)만 실호출 (opt-in). 상세 결과는 빈 배열이었음 |

스펙 출처는 **CJ대한통운 택배 표준 API Developer Guide V3.9.4**입니다. 원문은 저작권 고지 때문에 저장소에 포함하지 않습니다. 공개 배송조회는 계약 API가 아닌 비공식 웹 엔드포인트로, 변경되거나 차단될 수 있습니다. 선택적으로 실행할 때 직원 정보인 `crgNm`은 결과에서 제외합니다.

**ASSUMPTION:** 라벨 레이아웃은 CJ 표준 운송장 가이드를 확인하지 못해 가정한 미리보기입니다. 출력물은 승인된 운송장이 아니며 바코드 종류도 확인하지 못해 생성하지 않습니다. 모든 라벨에 가정 표시가 들어갑니다.

## 고지

이 프로젝트는 CJ대한통운과 무관한 개인 토이 프로젝트이며 CJ대한통운의 공식 SDK가 아닙니다. CJ 규격 문서(Developer Guide)의 원문은 포함하지 않고 필드명과 엔드포인트명을 사용합니다.

CJ 계약 API는 실서버에 호출한 적이 없으며 규격 기반 mock 서버로만 검증했습니다. 실제 호출은 공개 배송조회 웹페이지에 가짜 송장번호 `000000000000`으로 조회한 것뿐입니다. 라벨과 출력 레이아웃은 가정(ASSUMPTION)입니다.

## 실행

Python 3.13 기준, 런타임은 표준 라이브러리만 사용합니다.

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m cj_toy demo
```

데모는 임시 포트의 로컬 mock을 자동 시작하고 `out/`에 결과를 기록합니다. 테스트 데이터와 mock 고객 정보는 가짜입니다. 데모는 오류 주입을 위해 `CJ_BASE_URL`이 비어 있거나 기본 로컬 주소일 때만 실행합니다. 별도 서버와 CLI를 사용할 때는 같은 가짜 고객 정보를 환경변수로 설정합니다.

```sh
export CJ_CUST_ID=MOCK_CUSTOMER CJ_BIZ_REG_NUM=0000000000
PYTHONPATH=src .venv/bin/python -m cj_toy.mock_server --port 8765
# 다른 터미널에서 같은 환경변수 설정 후
PYTHONPATH=src .venv/bin/python -m cj_toy ship --sample
PYTHONPATH=src .venv/bin/python -m cj_toy track 650000000001
PYTHONPATH=src .venv/bin/python -m cj_toy cancel SAMPLE-001
```

공개 웹 조회는 명시적으로 실행할 때만 네트워크를 사용합니다.

```sh
PYTHONPATH=src .venv/bin/python -m cj_toy real-tracking 000000000000
```

CJ와 계약 후 발급받은 고객ID와 청구 사업자번호를 `CJ_CUST_ID`, `CJ_BIZ_REG_NUM`으로 지정하고 개발 서버 주소를 `CJ_BASE_URL`에 설정하면 같은 코드로 개발 서버에 연결할 수 있습니다. 개발 서버 접근은 CJ 승인이 필요할 수 있습니다. 운영 주소는 `https://dxapi.cjlogistics.com:5052`입니다.

```sh
CJ_BASE_URL=https://dxapi-dev.cjlogistics.com:5054 CJ_CUST_ID=... CJ_BIZ_REG_NUM=... PYTHONPATH=src .venv/bin/python -m cj_toy ship --sample
```

`.env.example`은 설정 예시이며 프로그램이 `.env`를 자동으로 읽지는 않습니다. `CJ_TIMEOUT`, `CJ_MAX_RETRIES`, `CJ_AUTH_RETRY_WAIT`도 환경변수로 설정할 수 있습니다.

## 오류 처리

| 상황 | 처리 |
| --- | --- |
| 주소 오류 `-20000`~`-20010` | `AddressRefineError`, 채번 전 중단 |
| `ORA-00001` | 로컬 성공 기록이 있으면 반환, 없으면 `DuplicateBookingError` |
| 네트워크 오류·타임아웃, 429, 5xx | 횟수 제한과 지수 백오프·지터를 적용해 재시도 |
| 400·403·404 및 업무 오류 | 재시도 없이 오류 반환 |
| 401 | 토큰 폐기 후 기본 60초 대기, 재발급하고 해당 호출을 한 번 재시도. `CJ_AUTH_RETRY_WAIT`으로 조정 가능. 가이드 p7에는 **1시간 후 재발급**과 **1분 이상 간격의 자동 재발급 추천**이 모두 기재되어 있으므로 실제 연동 시 CJ에 적정 대기 시간을 확인해야 함 |

토큰은 만료 30분 전 갱신하고 발급 요청 간격을 최소 1초로 둡니다. 로그는 JSON 한 줄 형식이며 이름 `홍길동 → 홍*동`, 전화 `010-0000-0000 → 010-****-0000`, 주소 `서울특별시 중구 ... → 서울특별시 중구***`, 토큰 앞 4자리와 사업자번호 끝 4자리만 남깁니다. 출력용 라벨과 로컬 예약 파일에는 인쇄 및 취소에 필요한 원문 정보가 저장되므로 접근 권한과 보관 기간을 관리해야 합니다.

## 실행 결과 일부

다음은 [실제 데모 기록](docs/demo-run.txt)에서 발췌했습니다.

```text
8. 운송장 650000000001 추적
   CRG_ST | 상태 | 처리일 | 처리시간 | 처리점소
   11 | 집화 | 20260101 | 120000 | 테스트 집배점
   41 | 간선 | 20260101 | 120000 | 테스트 집배점
   82 | 배송출발 | 20260101 | 120000 | 테스트 집배점
   91 | 배송완료 | 20260101 | 120000 | 테스트 집배점
API별 호출 횟수 (mock 서버 기준)
   ReqOneDayToken     2회
   ReqAddrRfnSm       10회
   ReqInvcNo          3회
   RegBook            3회
   CnclBook           1회
   ReqOneGdsTrc       1회
```

## 한계와 다음 단계

실제 CJ 계약 API 연결, 운송장 출력물과 스캔, 운영 승인 여부는 검증하지 않았습니다. mock의 분류 코드, 배송 이벤트와 송장 번호는 가상 데이터입니다. 로컬 저장소는 단일 프로세스용이며 여러 프로세스 간 동시성이나 접수 성공 직후 저장 실패를 보장하지 않습니다. 타임아웃 후 접수 성공 여부가 불명확할 수 있으므로 운영 환경에서는 CJ와 중복 확인 및 복구 절차를 마련하고 영속 저장소와 잠금을 도입해야 합니다. 실제 고객 계약에 맞는 필수값, 필드 길이와 대기 시간을 CJ와 재확인하고 승인된 표준 운송장 가이드로 출력·스캔을 검증해야 합니다.

## 라이선스

MIT 라이선스. [LICENSE](LICENSE) 파일을 참조하세요.
