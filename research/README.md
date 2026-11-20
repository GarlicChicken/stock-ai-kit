# research

자유롭게 탐색하는 곳입니다. 전략 파일과 달리 여기서는 파일 읽기 · 쓰기, 외부 연동(`kit.connectors`)을 써도 됩니다.
결과 파일은 `research/outputs/`에 저장합니다(저장소에 올라가지 않음).

## 예시 (`research/examples/`)

| 파일 | 하는 일 | 필요한 키 |
|---|---|---|
| `factor_lab.py` | 기본 신호 12종을 한꺼번에 검증 (IC · 5분위 · 다중 검정 보정) | 없음 |
| `macro_dashboard.py` | 코스피 · 기준금리 · 국고채 · 환율 · 물가 · 미국 지수를 같은 날짜로 모으기 (시점 맞춤) | ECOS (없으면 시험용 10건) |
| `dart_buyback_event.py` | 자기주식 취득 결정 공시 뒤 주가 흐름 (이벤트 스터디) | DART |
| `dart_profit_screen.py` | 영업이익이 해마다 늘어난 종목 찾기 (공시일 기준) | DART |
| `news_buzz.py` | 검색어의 날짜별 기사 수와 주가 | 네이버 |
| `kis_collect.py` | 오늘 분봉 · 투자자별 매매동향 받아 쌓기 | 한국투자증권 |

실행: `uv run python research/examples/<파일>.py --help`

## 직접 쓸 때

```python
from kit import data
from kit.config import load_config
from kit.lab import signals, factor_test
from kit.connectors import dart, ecos, world

cfg = load_config()
panel = data.load_panel(cfg)                 # 수정주가 표 · 투자 대상 · 종목 이름
res = factor_test.test(signals.compute(panel, "reversal_5"), panel, horizon=5)
print(res["summary"])
```

연동 설명: `docs/connectors.md` · 연구 방법: `docs/research-guide.md`
