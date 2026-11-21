# 전략 작성법

전략은 `strategies/` 폴더의 파이썬 파일 하나입니다. 새 파일은 `uv run kit new <이름>`으로 만듭니다.

## 기본 모양

```python
from kit.helpers import equal_weight, returns, top

NAME = "모멘텀 상위 10"                       # 화면에 나오는 이름
DESCRIPTION = "최근 60거래일 수익률 상위 10종목"   # 한 줄 설명
REBALANCE = "weekly"                          # daily · weekly · monthly · 2weeks · 3weeks · 10days · 2months


def decide(market):
    ret = returns(market.close, 60)           # 종목별 최근 60거래일 수익률
    if ret.empty:
        return {}                             # 데이터가 모자라면 전부 현금
    ret = ret[ret.index.isin(market.tradable())]
    return equal_weight(top(ret, 10))         # 상위 10종목을 같은 비중으로
```

## 언제 불리고, 언제 사고파나

1. 리밸런싱하는 날 **장이 끝난 뒤** `decide(market)`가 불립니다. 리밸런싱하는 날은 기간 첫날, 그리고 `REBALANCE`에 따라 아래와 같습니다.
2. 돌려준 비중대로 **다음 거래일 시가**에 사고팝니다. 목표에 없는 종목은 모두 팝니다.
3. 그 사이에는 들고 있는 종목을 그대로 둡니다. 들고 있던 종목이 상장폐지되면 마지막 가격으로 자동 정리됩니다.

| `REBALANCE` | 리밸런싱하는 날 |
|---|---|
| `"daily"` | 매일 |
| `"weekly"` · `"2weeks"` · `"3weeks"` | 매주 · 2주마다 · 3주마다 그 주의 마지막 거래일 |
| `"monthly"` · `"2months"` | 매달 · 2달마다 그 달의 마지막 거래일 |
| `"10days"` | 10거래일마다 |

'2주마다' 같은 주기는 달력에 고정되어 있어, 시작일이 달라도 같은 날에 리밸런싱합니다.

**살 수 있는 종목은 그날의 투자 대상뿐입니다.** 투자 대상은 지난달 마지막 거래일의 시가총액 상위 200개 보통주입니다(그때 기준이라 나중에 상장폐지된 종목도 들어 있음). 종목을 고를 때는 `market.tradable()`(투자 대상 중 오늘 거래된 종목) 안에서 고릅니다.

## decide가 돌려줄 수 있는 것

| 돌려주는 값 | 뜻 |
|---|---|
| `{코드A: 0.5, 코드B: 0.3}` | 조건으로 고른 종목 A 50%, B 30%, 나머지 20%는 현금 |
| `[코드A, 코드B]` | 목록의 종목을 같은 비중으로 (각 50%) |
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
| `market.market(code)` | 그날 기준 시장(KOSPI/KOSDAQ) |
| `market.sector(code)` · `market.sectors(codes)` | 업종 (섹터분산용, 아래 참고) |

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
| `limit_per_sector(codes, market, n)` | 앞에서부터 보며 업종마다 n종목까지만 남기기 (섹터분산) |
| `scale(weights, ratio)` | 비중을 ratio배로 (예: 0.5 = 절반만 투자하고 나머지는 현금) |

pandas로 직접 계산해도 됩니다. 예: 최근 20일 평균 거래대금 `market.amount.iloc[-20:].mean()`, 오늘 시가총액 `market.marcap.iloc[-1]`

## 업종 (섹터분산)

- 업종은 한국표준산업분류(KSIC)를 30개 남짓한 묶음(반도체·전자, 자동차, 은행·금융, 제약·바이오 등)으로 나눈 키트 업종표(`kit/reference/sectors.csv`)를 씁니다.
- **분산에만 씁니다.** 업종마다 몇 종목까지 담을지 정하는 데 쓰고, 특정 업종을 골라 사는 규칙(예: '반도체만')은 만들지 않습니다.
- 업종은 지금(마지막) 기준이라 오래전 업종 변경은 반영하지 않습니다. 업종을 찾지 못한 종목은 '미분류'입니다.

## 지켜야 할 것 (backtest · submit 때 자동 점검)

**이미 아는 결과로 고르지 않기**: 규칙은 모든 종목에 똑같이 적용되는 조건이어야 합니다.
- 종목코드 · 종목 이름 · 업종 이름을 코드에 직접 적지 않습니다 (`"005930"`, `"삼성전자"`, `"반도체·전자"` 등)
- 날짜 · 연도를 조건으로 쓰지 않습니다 (`"2023-03-02"`, `market.today.year == 2024` 등)
- `market.name()`으로 종목을 고르지 않습니다

**연구 기간**: 연구(backtest · lookahead · screen · factor · 연구 스크립트)는 설정의 연구 기간 끝(`research_end`)까지의 데이터만 봅니다. 그 뒤(모의투자 기간)는 `kit submit`으로만 계산합니다.

**안전**
- 파일 · 인터넷에 접근하지 않습니다: `open`, `pd.read_csv`, `to_csv`, `np.loadtxt`, `requests` 등
- import는 pandas · numpy · math · statistics · datetime · functools · itertools · collections · typing · dataclasses · `kit.helpers`만
- 무작위는 시드를 고정합니다: `rng = np.random.default_rng(42)`
- `decide` 밖에서 미리 계산해 두는 값(전역 변수)은 상수만 둡니다
- 밑줄(`_`)로 시작하는 내부 속성(`market._panel` 등)은 쓰지 않습니다

## 확인하는 순서

```bash
uv run kit backtest strategies/<파일>.py                 # 연구 기간 결과 (outputs/<파일 이름>/report.html)
uv run kit backtest strategies/<파일>.py --start 2016-01-04 --end 2019-12-30   # 기간을 나눠 다시 보기
uv run kit lookahead strategies/<파일>.py                # 미래 데이터 · 무작위 검사
uv run kit submit strategies/<파일>.py --name <이름> --team <팀 이름>   # 모의투자 기간 결과 CSV (마지막에 한 번)
```

## 자주 쓰는 말

| 말 | 뜻 |
|---|---|
| 일봉 | 하루 한 줄짜리 가격 (시가 · 고가 · 저가 · 종가 · 거래량) |
| 이동평균 (20일선 · 60일선) | 최근 n거래일 종가의 평균. 주가가 평균 위면 오르는 흐름으로 봄 |
| 수익률 | 일정 기간 동안 오른 비율. `returns(close, 60)` = 최근 60거래일 수익률 |
| 거래대금 | 그날 사고판 금액 (주가 × 거래량) |
| 시가총액 | 회사 전체 주식의 가치 (주가 × 주식 수). 큰 회사 · 작은 회사를 나누는 기준 |
| 리밸런싱 | 정한 주기마다 종목 · 비중을 다시 맞추는 것 |
| 동일 비중 | 고른 종목에 돈을 똑같이 나눠 담기 |
| 최대 낙폭 (MDD) | 가장 높았던 때에서 가장 크게 떨어진 비율 |
| 현금 비중 | 전체 돈 가운데 주식을 사지 않고 남겨 둔 비율 |

## 전략 아이디어 (예시 파일 `strategies/examples/`)

| 방법 | 생각 | 예시 파일 |
|---|---|---|
| 동일 비중 | 큰 종목들에 골고루 | `equal_weight.py` (시가총액 상위, 매달) |
| 골든크로스 | 단기 평균이 장기 평균을 뚫고 오르면 산다 | `golden_cross.py` |
| 모멘텀 | 최근 많이 오른 종목이 조금 더 오른다 | `momentum.py` |
| 추세추종 | 평균선 위에 있는 오르는 종목만 들고 간다 | `trend_following.py` (2주마다) |
| 눌림목 | 오르는 흐름 속 잠깐 내린 때 산다 | `pullback.py` |
| 섹터분산 | 한 업종에 몰리지 않게 나눠 담는다 | `sector_spread.py` |
| 현금 비중 조절 | 시장 분위기가 나쁘면 일부 · 전부 현금 | `market_timing.py` |

이 밖에 해 볼 만한 것: 단기 되돌림(최근 며칠 많이 내린 종목), 저변동성(덜 흔들린 종목), 거래대금 급증,
52주 신고가 근처, 소형주 · 대형주, 손절 · 익절 규칙, 여러 신호 섞기. 신호만 먼저 검증하려면 `uv run kit factor list`.
