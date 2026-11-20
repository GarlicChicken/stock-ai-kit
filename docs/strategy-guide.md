# 전략 작성법

전략은 `strategies/` 폴더의 파이썬 파일 하나입니다. 새 파일은 `uv run kit new <이름>`으로 만듭니다.

## 기본 모양

```python
from kit.helpers import equal_weight, returns, top

NAME = "모멘텀 상위 10"                       # 화면에 나오는 이름
DESCRIPTION = "최근 60거래일 수익률 상위 10종목"   # 한 줄 설명
REBALANCE = "weekly"                          # daily(매일) · weekly(매주) · monthly(매달)


def decide(market):
    ret = returns(market.close, 60)           # 종목별 최근 60거래일 수익률
    if ret.empty:
        return {}                             # 데이터가 모자라면 전부 현금
    ret = ret[ret.index.isin(market.tradable())]
    return equal_weight(top(ret, 10))         # 상위 10종목을 같은 비중으로
```

## 언제 불리고, 언제 사고파나

1. 리밸런싱하는 날(기간 첫날, 그리고 매일 · 매주 마지막 거래일 · 매달 마지막 거래일) **장이 끝난 뒤** `decide(market)`가 불립니다.
2. 돌려준 비중대로 **다음 거래일 시가**에 사고팝니다. 목표에 없는 종목은 모두 팝니다.
3. 그 사이에는 들고 있는 종목을 그대로 둡니다. 들고 있던 종목이 상장폐지되면 마지막 가격으로 자동 정리됩니다.

**살 수 있는 종목은 그날의 투자 대상뿐입니다.** 투자 대상은 지난달 마지막 거래일의 시가총액 상위 200개 보통주입니다(그때 기준이라 나중에 상장폐지된 종목도 들어 있음). 종목을 고를 때는 `market.tradable()`(투자 대상 중 오늘 거래된 종목) 안에서 고릅니다.

## decide가 돌려줄 수 있는 것

| 돌려주는 값 | 뜻 |
|---|---|
| `{"005930": 0.5, "000660": 0.3}` | 삼성전자 50%, SK하이닉스 30%, 나머지 20%는 현금 |
| `["005930", "000660"]` | 목록의 종목을 같은 비중으로 (각 50%) |
| `{}` 또는 `None` | 전부 현금 |
| `KEEP` (`from kit.helpers import KEEP`) | 이번에는 사고팔지 않고 들고 있는 그대로 둠 |

- 비중 합이 1을 넘으면 1에 맞게 줄입니다. 0 이하 비중과 투자 대상이 아닌 종목은 무시합니다.
- 공매도 · 신용(빚)은 없습니다.

## market에 들어 있는 것

| 이름 | 내용 |
|---|---|
| `market.today` | 오늘 날짜 |
| `market.close` · `open` · `high` · `low` · `volume` | 날짜 × 종목코드 표 (수정주가 · 수정 거래량). **마지막 줄이 오늘**이고, 그 뒤 데이터는 없습니다 |
| `market.amount` | 거래대금 표 (원) |
| `market.marcap` | 시가총액 표 (원) |
| `market.dates` | 오늘까지의 거래일 |
| `market.universe()` | 오늘의 투자 대상 (지난달 말 시가총액 상위 200개) |
| `market.tradable()` | 투자 대상 중 오늘 정상 거래된 종목 |
| `market.price()` | 오늘 실제 종가 (수정 전, 원). 주가 수준(예: 1,000원 미만 제외)을 볼 때 씁니다 |
| `market.holdings` | 지금 들고 있는 종목과 비중 `{종목코드: 비중}` |
| `market.codes` | 데이터에 있는 모든 종목코드 (지금은 투자 대상이 아닌 종목도 포함) |
| `market.name(code)` · `market.market(code)` | 그날 기준 종목 이름 · 시장(KOSPI/KOSDAQ) |

- 가격 표는 수정주가입니다(액면분할 · 증자 등을 반영해 2024-12-30 종가를 실제 가격과 맞춘 값). 그래서 오래전 가격은 그때 실제 가격과 다릅니다. 그날 실제 가격은 `market.price()`로 봅니다.
- 상장 전 · 상장폐지 뒤 날짜는 값이 비어 있습니다(NaN). 표에는 투자 대상이 아닌 종목도 있으니, 전체 표로 순위를 매길 때는 `market.tradable()`로 걸러 씁니다.

## 도구 (`kit.helpers`)

| 함수 | 하는 일 |
|---|---|
| `returns(close, n)` | 종목별 최근 n거래일 수익률 |
| `sma(close, n)` | 종목별 최근 n거래일 이동평균 (n일 중 빈 값이 있는 종목은 제외) |
| `top(values, n)` · `bottom(values, n)` | 값이 큰 · 작은 순서로 n개 종목코드 |
| `equal_weight(codes)` | 같은 비중 `{종목코드: 1/개수}` |
| `only(values, codes)` | codes에 든 종목만 남기기 |

pandas로 직접 계산해도 됩니다. 예: 최근 20일 평균 거래대금 `market.amount.iloc[-20:].mean()`, 오늘 시가총액 `market.marcap.iloc[-1]`

## 지켜야 할 것 (제출 점검에서 확인)

- 파일 · 인터넷에 접근하지 않습니다: `open`, `pd.read_csv`, `to_csv`, `np.loadtxt`, `requests` 등
- import는 pandas · numpy · math · statistics · datetime · functools · itertools · collections · typing · dataclasses · `kit.helpers`만
- 무작위는 시드를 고정합니다: `rng = np.random.default_rng(42)`
- `decide` 밖에서 미리 계산해 두는 값(전역 변수)은 상수만 둡니다
- 밑줄(`_`)로 시작하는 내부 속성(`market._panel` 등)은 쓰지 않습니다

## 확인하는 순서

```bash
uv run kit backtest strategies/<파일>.py      # 결과 보기 (outputs/<파일 이름>/report.html)
uv run kit lookahead strategies/<파일>.py     # 미래 데이터 · 무작위 검사
uv run kit submit strategies/<파일>.py --name <이름> --start <시작일> --end <끝 날짜>   # 진행자에게 보낼 결과 CSV
```
