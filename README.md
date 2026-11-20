# stock-ai-kit

국내 주식을 연구하는 데 필요한 것들을 한곳에 모은 파이썬 키트입니다.
데이터 받기 · 외부 연동 · 백테스트(시뮬레이션) · 신호 검증 · 결과 비교를 모듈로 나눠 두었고,
모두 같은 데이터 · 같은 규칙 · 같은 결과 양식으로 동작합니다.

> 실제 주문 기능은 없습니다. 과거 데이터로 하는 모의 실험이며 투자 권유가 아닙니다.

## 들어 있는 것

| 모듈 | 하는 일 | 문서 |
|---|---|---|
| 표준 데이터 (`kit.data`) | 한국거래소 일별 데이터(2000~), 매달 그때의 시가총액 상위 200종목, **상장폐지 종목 포함**, 수정주가, 데이터 지문 | [데이터 출처](docs/data-sources.md) |
| 외부 연동 (`kit.connectors`) | DART 공시 · 재무제표, 네이버 뉴스, 한국은행 ECOS, 한국투자증권(조회), KRX, 해외 지수 · 미국 경제지표 | [외부 연동](docs/connectors.md) |
| 백테스트 (`kit.engine`) | 다음 날 시가 체결, 수수료 · 연도별 증권거래세, 거래정지 · 상장폐지 처리, 투자 대상 밖 종목 차단 | [백테스트 규칙](docs/rules.md) · [전략 작성법](docs/strategy-guide.md) |
| 연구 도구 (`kit.lab`) | 기본 신호 12종, 신호 검증(IC · 5분위), 우연 검사(플라시보 · 신뢰구간 · 다중 검정 보정), 이벤트 스터디, 거래일 · 공시 시점 처리 | [연구 방법](docs/research-guide.md) |
| 결과 양식 (`kit.result`) | 모든 결과를 같은 CSV(날짜별 평가금액)로 저장 · 점검 | [결과 CSV 양식](docs/result-spec.md) |
| 수익 레이스 (`race.html`) | 여러 결과 CSV를 끌어다 놓으면 평가금액 그래프와 순위가 움직이며 재생 | [결과 모아 비교하기](docs/race.md) |

## 설치

| | 윈도우 | 맥 |
|---|---|---|
| 1. uv 설치 | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| 2. 키트 받기 | [ZIP 받기](https://github.com/GarlicChicken/stock-ai-kit/archive/refs/heads/main.zip) → `C:\stock-ai-kit` | [ZIP 받기](https://github.com/GarlicChicken/stock-ai-kit/archive/refs/heads/main.zip) → `~/stock-ai-kit` |
| 3. 설치 | `uv sync --locked` | `uv sync --locked` |
| 4. 점검 | `uv run kit check` | `uv run kit check` |
| 5. 데이터 | `uv run kit data download` 또는 받은 zip을 `uv run kit data unpack <zip>` | 같음 |

키트 폴더는 영문 짧은 경로에 둡니다(한글 경로 · OneDrive 동기화 폴더는 피함).
파이썬 3.13과 패키지 버전이 `uv.lock`으로 고정되어 윈도우 · 맥 어디서나 같은 숫자가 나옵니다.

## 명령

키트 폴더에서 `uv run kit <명령>`으로 실행합니다. `uv run kit --help`로 전체 목록을 봅니다.

| 분류 | 명령 | 하는 일 |
|---|---|---|
| 점검 | `check` · `sources` | 설치 점검(샘플 기준값) · 데이터 출처 연결 점검 |
| 데이터 | `data download` · `unpack` · `pack` · `verify` · `info` · `calendar` · `minute` | 받기 · 풀기 · 묶기 · 지문 확인 · 현황 · 거래일 목록 · 분봉 쌓기 |
| 외부 연동 | `keys` · `keys set <이름>` · `keys test` | 키 보기 · 설정(터미널에서 직접 입력) · 연결 점검 |
| 전략 | `new` · `backtest` · `lookahead` · `screen` | 새 전략 · 백테스트(`--cost-x`로 비용 민감도) · 미래 데이터 검사 · 그날 고르는 종목 |
| 연구 | `factor list` · `factor <신호>` · `event <CSV>` | 신호 목록 · 신호 검증 · 이벤트 스터디 |
| 결과 | `submit` · `validate` · `race` | 정한 기간의 결과 CSV 만들기 · 양식 점검 · 수익 레이스 |

## 폴더

```
stock-ai-kit/
├ strategies/          전략 파일 (examples/ 예시 3개)
├ research/            자유 연구 · examples/ 연동 · 연구 도구 사용 예시
├ data/                표준 데이터 (저장소에 없음)
├ outputs/             결과 CSV · 리포트
├ submissions/         모으는 결과 CSV
├ kit/                 엔진
│  ├ connectors/       외부 연동 (dart · naver_news · ecos · kis · krx · world)
│  └ lab/              연구 도구 (signals · factor_test · robustness · event_study · calendar)
├ config/              공통 설정
├ docs/                설명서
├ race.html            수익 레이스 화면
└ .env.example         외부 연동 키 자리 (실제 키는 .env, 저장소에 올라가지 않음)
```

## 업데이트

새 버전은 ZIP을 다시 받아 키트 폴더를 바꾸고, 내 `strategies/` · `research/` · `.env`만 옮겨 옵니다.
그다음 `uv sync --locked`와 `uv run kit check`를 다시 실행합니다.

## 사용한 오픈소스 · 데이터

[FinanceData/marcap](https://github.com/FinanceData/marcap) · [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) · [pykrx](https://github.com/sharebook-kr/pykrx) · [yfinance](https://github.com/ranaroussi/yfinance) · [pandas](https://pandas.pydata.org) · [numpy](https://numpy.org) · [pyarrow](https://arrow.apache.org) · [uv](https://github.com/astral-sh/uv) ·
OpenDART · NAVER API HUB · 한국은행 ECOS · 한국투자증권 Open API · KRX Open API · FRED
