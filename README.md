# cj-logistics-api-client

Python client and test mock server for the CJ Logistics parcel standard API (V3.9.4).

CJ대한통운 택배 표준 API(V3.9.4) 규격에 맞춰 주소 정제, 운송장 채번, 예약 접수, 취소, 배송 추적을 하나의 흐름으로 연결한 Python 연동 모듈입니다. 런타임은 표준 라이브러리만 사용하므로 별도 패키지를 설치하지 않아도 동작합니다.

## 주요 기능

- **접수 흐름 자동화**: 받는 사람 주소를 먼저 정제하고, 운송장 번호를 채번한 뒤 예약을 접수합니다. 접수 결과는 분류 코드가 포함된 출력 데이터로 바로 이어집니다.
- **오류 처리**
  - 주소 오류(`-20000`~`-20010`)가 발생하면 채번하기 전에 중단하므로 운송장 번호가 낭비되지 않습니다.
  - 네트워크 오류, 타임아웃, 429, 5xx 응답은 지수 백오프와 지터를 적용해 정해진 횟수만큼 재시도합니다.
  - 토큰이 만료되면(401) 토큰을 폐기하고 재발급한 뒤 해당 호출을 다시 시도합니다.
  - 같은 고객사용번호(`CUST_USE_NO`)로 다시 요청하면 저장된 결과를 돌려주고, CJ 서버가 중복(`ORA-00001`)으로 응답하는 경우도 구분해 처리합니다.
- **개인정보 마스킹 로그**: 모든 API 요청과 응답을 JSON 한 줄 형식으로 기록하며, 이름·전화번호·주소·토큰·사업자번호는 가려서 남깁니다.
- **출력 데이터**: 운송장 번호, 분류 코드(`CLSFCD`, `SUBCLSFCD`), 집배점 정보와 송·수하인 정보를 JSON, CSV, HTML 미리보기로 만듭니다.
- **테스트용 mock 서버 포함**: 규격(V3.9.4)에 따라 정상 응답과 오류 코드를 재현하므로 계약 정보 없이도 정상·오류 시나리오를 모두 실행해 볼 수 있습니다.
- **pytest 테스트 47개**: 정상 흐름과 오류 처리 시나리오를 자동으로 검증합니다.
- **환경변수로 서버 전환**: 고객사 계약 정보(`CJ_CUST_ID`, `CJ_BIZ_REG_NUM`)와 `CJ_BASE_URL`을 환경변수로 지정하면 같은 코드로 CJ 개발 서버나 운영 서버에 연결합니다. 계약 정보는 코드에 하드코딩하지 않습니다.

## 구조

```text
CLI → ShipmentService → CJClient (토큰 관리, 재시도) → CJ API (mock | 개발 | 운영)
              ├→ 출력 데이터 (JSON / CSV / HTML)
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

- `src/cj_toy/client.py`, `constants.py`: CJ API 요청, 토큰 관리, 재시도, API 경로와 오류 코드를 담당합니다.
- `service.py`, `models.py`, `label.py`: 입력 검증, 접수와 멱등성 처리, JSON·CSV·HTML 출력을 담당합니다.
- `mock_server.py`, `logging_utils.py`: 테스트용 mock 서버와 마스킹된 구조화 로그를 담당합니다.
- `cli.py`, `public_tracking.py`: 데모와 명령행 기능, 공개 배송조회 웹페이지 조회 기능을 제공합니다.
- `tests/`: mock 서버를 사용하는 통합 테스트와 단위 테스트가 들어 있습니다. `docs/`에는 실제 실행 기록이 있습니다.

## 실행

Python 3.13 기준입니다. 테스트에만 pytest가 필요합니다.

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m cj_toy demo
```

데모는 임시 포트에서 mock 서버를 자동으로 시작하고, 정상 접수부터 오류 시나리오까지 차례로 실행한 뒤 결과를 `out/`에 기록합니다. 샘플 데이터는 모두 가상의 값입니다.

mock 서버와 CLI를 따로 실행할 수도 있습니다.

```sh
export CJ_CUST_ID=MOCK_CUSTOMER CJ_BIZ_REG_NUM=0000000000
PYTHONPATH=src .venv/bin/python -m cj_toy.mock_server --port 8765
# 다른 터미널에서 같은 환경변수를 설정한 뒤
PYTHONPATH=src .venv/bin/python -m cj_toy ship --sample
PYTHONPATH=src .venv/bin/python -m cj_toy track 650000000001
PYTHONPATH=src .venv/bin/python -m cj_toy cancel SAMPLE-001
```

CJ 공개 배송조회 웹페이지로 송장을 조회하는 명령도 있습니다. 이 명령은 실행할 때만 네트워크를 사용합니다.

```sh
PYTHONPATH=src .venv/bin/python -m cj_toy real-tracking <운송장번호>
```

### CJ 서버 연결

CJ와 계약해 발급받은 고객ID와 사업자번호를 `CJ_CUST_ID`, `CJ_BIZ_REG_NUM`에 지정하고 서버 주소를 `CJ_BASE_URL`에 지정합니다. 개발 서버는 `https://dxapi-dev.cjlogistics.com:5054`, 운영 서버는 `https://dxapi.cjlogistics.com:5052`입니다.

```sh
CJ_BASE_URL=https://dxapi-dev.cjlogistics.com:5054 CJ_CUST_ID=... CJ_BIZ_REG_NUM=... PYTHONPATH=src .venv/bin/python -m cj_toy ship --sample
```

`CJ_TIMEOUT`, `CJ_MAX_RETRIES`, `CJ_AUTH_RETRY_WAIT`로 타임아웃, 재시도 횟수, 토큰 재발급 대기 시간을 조정할 수 있습니다. `.env.example`에 설정 예시가 있으며, 프로그램이 `.env` 파일을 자동으로 읽지는 않습니다.

## 오류 처리

| 상황 | 처리 |
| --- | --- |
| 주소 오류 `-20000`~`-20010` | `AddressRefineError`를 발생시키고 채번 전에 중단합니다 |
| 중복 접수 `ORA-00001` | 로컬 성공 기록이 있으면 그 결과를 반환하고, 없으면 `DuplicateBookingError`를 발생시킵니다 |
| 네트워크 오류, 타임아웃, 429, 5xx | 지수 백오프와 지터를 적용해 정해진 횟수만큼 재시도합니다 |
| 400, 403, 404, 업무 오류 | 재시도하지 않고 오류를 반환합니다 |
| 토큰 만료 401 | 토큰을 폐기하고 대기한 뒤(기본 60초, `CJ_AUTH_RETRY_WAIT`로 조정) 재발급하고 해당 호출을 한 번 다시 시도합니다 |

토큰은 만료 30분 전에 미리 갱신하며, 토큰 발급 요청 사이에는 최소 1초 간격을 둡니다. 로그에서는 이름 `홍길동`이 `홍*동`으로, 전화번호 `010-0000-0000`이 `010-****-0000`으로, 주소 `서울특별시 중구 ...`가 `서울특별시 중구***`로 바뀝니다. 토큰은 앞 4자리만, 사업자번호는 끝 4자리만 남깁니다.

## 실행 결과 일부

아래 내용은 [데모 실행 기록](docs/demo-run.txt)에서 발췌했습니다.

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

## 고지

이 프로젝트는 CJ대한통운과 무관한 비공식 프로젝트이며 CJ대한통운의 공식 SDK가 아닙니다. CJ 규격 문서(Developer Guide)의 원문은 포함하지 않으며, 코드에는 필드명과 엔드포인트명만 사용했습니다.

## 라이선스

MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
