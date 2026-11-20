# 외부 연동 (`kit.connectors`)

표준 데이터(가격 · 투자 대상) 밖의 자료를 가져오는 모듈입니다. research 스크립트에서 불러 씁니다
(전략 파일에서는 쓸 수 없음: 백테스트 재현성 · 미래 데이터 차단 때문).

| 모듈 | 가져오는 것 | 키 | 무료 한도 | 실제 호출 확인 (2026-11-20) |
|---|---|---|---|---|
| `dart` | 공시 목록 · 기업 개황 · 재무제표(한 회사 · 여러 회사) | `DART_API_KEY` | 키당 하루 약 2만 건 | 확인 |
| `naver_news` | 뉴스 검색 · 날짜별 기사 수 | `NAVER_HUB_CLIENT_ID/SECRET` (또는 기존 `NAVER_CLIENT_ID/SECRET`) | 하루 25,000회 | 공식 문서 기준 (미시험) |
| `ecos` | 금리 · 환율 · 물가 · 통화량 등 한국은행 통계 | `ECOS_API_KEY` (없으면 시험용 10건) | 공식 안내 확인 | 확인 |
| `kis` | 현재가 · 일봉 · 오늘 분봉 · 투자자별 매매동향 (조회만) | `KIS_APP_KEY/SECRET`, `KIS_ENV` | 실전 초당 약 20건 | 조회 방식 정리 (미시험) |
| `krx` | 하루치 전 종목 공식 시세 | `KRX_AUTH_KEY` | 키당 하루 1만 건 | 확인 |
| `world` | 해외 지수 · 환율 · 원자재(yfinance), 미국 경제지표(FRED) | 없음 | 없음 | 확인 |

## 키 설정

1. 아래 '발급하는 곳'에서 키를 받습니다(대부분 무료 회원가입).
2. 키트 폴더 터미널에서 직접 실행합니다. 값은 화면에 보이지 않고 `.env`에 저장됩니다.
   ```bash
   uv run kit keys set DART_API_KEY
   ```
   `.env.example`을 `.env`로 복사해 직접 적어도 됩니다.
3. 확인합니다.
   ```bash
   uv run kit keys          # 어떤 키가 설정됐는지 (값은 끝 3자리만)
   uv run kit keys test     # 키가 있는 연동마다 실제로 한 번 호출
   ```
- `.env`는 저장소에 올라가지 않습니다(`.gitignore`). 키는 사람마다 따로 받고 나눠 쓰지 않습니다.
- 키는 AI 대화창에 붙여 넣지 말고 터미널에서 직접 넣습니다.
- 모든 호출은 같은 출처끼리 간격을 띄우고(호출 한도 보호), 429 · 5xx · 네트워크 오류는 2 · 4 · 8초 기다렸다가 다시 시도합니다.
- 캐시는 `.cache/connectors/<출처>/`에 둡니다(DART 고유번호 7일, 한국투자증권 토큰 만료 전까지).

---

## DART (`kit.connectors.dart`)

**발급하는 곳**: https://opendart.fss.or.kr > 인증키 신청 (무료)

| 함수 | 돌려주는 것 |
|---|---|
| `filings(stock_code=None, start, end, kind=None)` | 공시 목록: date(접수일) · corp_name · stock_code · report(보고서명) · rcept_no · url. `kind`: A 정기 · B 주요사항 · C 발행 · D 지분 · E 기타 · I 거래소 등 |
| `company(stock_code)` | 기업 개황: 회사명 · 대표자 · 업종코드 · 결산월 · 설립일 등 |
| `financials(stock_code, year, report="annual", full=False)` | 재무제표: 주요 계정(full=False) 또는 전체 계정. this_term · prev_term · prev2_term(원) · available_date(공시일) |
| `key_accounts(stock_code, years)` | 여러 해의 매출액 · 영업이익 · 당기순이익 표 |
| `key_accounts_many(stock_codes, year)` | 여러 회사(100개씩 묶음)의 한 해 매출액 · 영업이익 · 당기순이익 |
| `corp_codes()` · `corp_code(stock_code)` | 회사 고유번호 표 · 종목코드 → 고유번호 |

```python
from kit.connectors import dart
dart.filings("005930", start="2024-01-01")                # 삼성전자 공시
dart.filings(kind="B", start="2024-11-01", end="2024-11-30")  # 한 달 주요사항보고 전체
dart.key_accounts("005930", [2021, 2022, 2023, 2024])
```

**알아 둘 것**
- 공시 목록에는 접수 날짜만 있고 시각이 없습니다. 장 마감 뒤 접수가 적지 않으므로, 보수적으로 '접수일 장 마감 뒤에 알았다 → 다음 거래일 시가에 반응'으로 봅니다(`kit.lab.calendar.effective_day`).
- 재무제표 숫자는 사업연도 끝이 아니라 **공시일(available_date)부터** 쓸 수 있습니다. 백테스트 · 종목 고르기에서는 기준일까지 공시된 보고서만 씁니다.
- 공시일은 권리락일 · 효력 발생일이 아닙니다.
- 보고서명 가운뎃점이 'ㆍ' · '·'로 섞여 와서 '·'로 맞춥니다. 정정 공시는 이름에 '[기재정정]' 등이 붙습니다.
- 전체 공시 조회는 90일 단위로 나눠 받습니다(하루 수백~천여 건). 상태 코드 013(데이터 없음)은 정상으로, 020은 하루 한도 초과입니다.

예시: `research/examples/dart_buyback_event.py`(자기주식 취득 공시 이벤트 스터디), `dart_profit_screen.py`(영업이익 연속 증가 종목)

---

## 네이버 뉴스 (`kit.connectors.naver_news`)

**발급하는 곳**
- 새 방식(2026-06~): 네이버 클라우드 콘솔 > NAVER API HUB > Application 등록(검색 API 선택) > [인증 정보]의 Client ID · Client Secret → `NAVER_HUB_CLIENT_ID` · `NAVER_HUB_CLIENT_SECRET`
- 기존 방식: 네이버 개발자센터 키 → `NAVER_CLIENT_ID` · `NAVER_CLIENT_SECRET` (신규 발급 중단, 2027-06-30까지 사용 가능으로 알려짐)
- 두 방식의 키는 서로 바꿔 쓸 수 없습니다. 새 방식 키가 있으면 그것을 먼저 씁니다.

| 함수 | 돌려주는 것 |
|---|---|
| `search(query, count=100, sort="date")` | published(한국 시각) · title · description · originallink · link (최대 1,000건) |
| `daily_counts(query)` | 날짜별 기사 수 |

**알아 둘 것**
- 검색어 하나로 최근 기사 최대 1,000건까지만 받을 수 있어 오래된 기간은 볼 수 없습니다. 꾸준히 보려면 매일 받아 쌓습니다.
- 기사 수는 늘 기사가 많은 대형주에서 크게 나옵니다. 종목끼리 비교하지 말고 '같은 종목의 평소 대비'로 봅니다.
- 15:30 이후 기사는 다음 거래일 결정에 씁니다.
- 이용 범위는 네이버 약관을 따릅니다(기사 본문 수집 · 재배포 용도 아님).
- 공식 문서: https://api.ncloud-docs.com/docs/naver-api-hub-search-news

예시: `research/examples/news_buzz.py`

---

## 한국은행 ECOS (`kit.connectors.ecos`)

**발급하는 곳**: https://ecos.bok.or.kr/api > 인증키 신청 (무료). 키가 없으면 시험용 키로 한 번에 10건까지.

| 함수 | 돌려주는 것 |
|---|---|
| `get(이름, 시작, 끝)` | 자주 쓰는 지표: 기준금리 · 국고채3년 · 국고채10년 · 원달러환율(일) · 소비자물가 · M2(월) |
| `series(통계표코드, 주기, 시작, 끝, 항목코드...)` | 아무 통계: date · value · unit |
| `search_tables(검색어)` · `items(통계표코드)` | 통계표 · 항목 코드 찾기 (예: '시장금리', '환율', '통화', '물가') |
| `key_stats()` | 한국은행 100대 통계지표 최근 값 |

```python
from kit.connectors import ecos
ecos.get("기준금리", "20200101", "20241231")      # 일간: YYYYMMDD
ecos.get("소비자물가", "202001", "202412")         # 월간: YYYYMM
ecos.search_tables("시장금리")
```

**알아 둘 것**: 기준일과 발표일이 다릅니다. 월간 지표는 다음 달에 발표되므로 최소 한 달 늦춰 주가와 붙입니다.

예시: `research/examples/macro_dashboard.py`

---

## 한국투자증권 (`kit.connectors.kis`, 조회만)

**발급하는 곳**: https://apiportal.koreainvestment.com (계좌 개설 뒤 API 신청). 모의투자와 실전은 앱키가 따로입니다.
`KIS_ENV`: `mock`(모의투자 서버, 기본) · `real`(실전 서버)

| 함수 | 돌려주는 것 |
|---|---|
| `price(code)` | 현재가 · 등락률 · 거래량 · 거래대금 · 외국인 소진율 · 상장주식수 |
| `daily(code, start, end, adjusted=True)` | 일봉(수정주가 기본). 100행씩 뒤로 넘기며 받음 |
| `minutes_today(code)` | 오늘 1분봉 (30개씩 거꾸로 09:00까지) |
| `investor_flows(code)` | 최근 약 30거래일 개인 · 외국인 · 기관 순매수(수량 · 금액 원) |

**알아 둘 것**
- 접근 토큰은 앱키당 1분에 1번만 발급됩니다. 받은 토큰을 `.cache`에 두고 만료 60초 전까지 다시 씁니다. 같은 앱키를 쓰는 다른 프로그램이 있으면 토큰이 겹칠 수 있습니다.
- 실전은 초당 약 20건 제한(넘으면 EGW00201)이라 호출 사이를 띄웁니다. 모의 서버는 응답이 느립니다.
- 응답 값은 모두 문자열이고 API마다 단위가 다릅니다(투자자 순매수 대금은 백만원). 이 모듈은 금액을 원으로 바꿔 돌려줍니다.
- 투자자별 매매동향은 장 마감 뒤 공표되고, 오늘 행은 장 마감 전에는 비어 있습니다. 수급 신호는 다음 거래일 결정에만 씁니다.
- 분봉 시각은 봉이 시작한 시각입니다. 실제로 쓸 수 있는 건 그 봉이 끝난 뒤입니다.
- 무료 분봉은 오래 보관되지 않습니다. 매일 받아 쌓습니다.

예시: `research/examples/kis_collect.py`

---

## KRX (`kit.connectors.krx`)

**발급하는 곳**: https://openapi.krx.co.kr > 인증키 신청 > 쓸 API(유가증권 · 코스닥 일별매매정보)마다 이용 신청 · 승인

| 함수 | 돌려주는 것 |
|---|---|
| `daily(date, market="KOSPI")` | 그날 전 종목 시가 · 고가 · 저가 · 종가 · 거래량 · 거래대금 · 시가총액 (KOSPI · KOSDAQ) |

**알아 둘 것**: 약관상 받은 데이터를 다른 사람에게 다시 나눠 주면 안 됩니다. 값은 그날 실제 가격입니다(수정주가 아님으로 보임).

---

## 해외 (`kit.connectors.world`, 키 없음)

| 함수 | 돌려주는 것 |
|---|---|
| `prices(symbol, start)` | yfinance 일봉 종가 (분할 · 배당 반영). 예: `^GSPC` · `^IXIC` · `^SOX` · `^VIX` · `KRW=X` · `CL=F` · `GC=F` · `^N225` |
| `fred(series_id, start)` | 미국 경제지표. 예: `DGS10`(10년 금리) · `FEDFUNDS` · `CPIAUCSL` · `DEXKOUS` |

**시점 맞추기**
- 미국 시장은 한국 장이 끝난 뒤 열립니다. 한국 t일 장 마감 뒤 결정에는 미국 t-1일 종가까지 씁니다.
- 환율 · 원자재 · 암호화폐 일봉은 날짜 경계가 한국 개장 무렵이라 한국 t일 결정에는 t-2일 값까지 쓰는 편이 안전합니다.
- FRED 값은 지금 기준 최신값이라, 나중에 고쳐진 숫자가 섞여 있습니다(발표 당시 값이 아님).

---

## 그 밖에 (모듈 없음, 참고)

| 출처 | 쓰임 | 비고 |
|---|---|---|
| 키움증권 REST API | 시세 · 분봉 | 키 자리만 `.env.example`에 마련. 공식 예제 저장소 참고 |
| 공공데이터포털 금융위원회 주식시세 | 공식 시세 | 키 필요, 재배포 금지 |
| 공공데이터포털 특일 정보 | 공휴일 | 공휴일과 거래소 휴장일은 다름. 거래일은 데이터에 실제로 있는 날짜로 정하는 편이 안전 |

새 출처를 더할 때는 `kit/connectors/base.py`의 `get_key` · `request` · `cache_dir`를 쓰고, 표(DataFrame)로 돌려주며, `ping()` 함수를 두면 `kit keys test`에 바로 붙습니다(`kit/connectors/__init__.py`의 `GROUPS`).
