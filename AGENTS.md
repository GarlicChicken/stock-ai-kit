# 저장소 작업 규칙 (stock-ai-kit)

국내 주식 연구 키트입니다. 데이터 · 외부 연동 · 백테스트 · 연구 도구 · 결과 양식을 모듈로 나눠 두었습니다.
여러 사람이 같은 데이터 · 같은 규칙으로 결과를 내고 비교할 수 있게 하는 것이 목적이라, 아래 규칙을 지킵니다.

## 고치지 않는 것
- `kit/`(엔진 · 연동 · 연구 도구), `config/`, `data/`, `race.html`
- `pyproject.toml`, `uv.lock`, `.python-version`, `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.github/`
- 패키지를 추가하거나 버전을 바꾸지 않습니다 (`uv add` · `pip install` · `uv lock --upgrade` 금지).

작업하는 곳은 `strategies/`(전략 파일)와 `research/`(자유 연구)입니다.

## 실행
- 파이썬은 항상 `uv run`으로 실행합니다. 예: `uv run kit check`, `uv run python research/examples/factor_lab.py`
- 명령 목록: `uv run kit --help` · 문서: `README.md`

## 키 · 주문
- 외부 연동 키는 `.env`에만 있습니다. 키 값을 묻거나, 출력하거나, 다른 파일에 적지 않습니다.
  키 설정은 사용자가 터미널에서 직접 `uv run kit keys set <이름>`으로 합니다. 확인은 `uv run kit keys test`.
- 주문(매수 · 매도) 기능은 없고 만들지 않습니다. 연동은 조회만 합니다.

## 전략 파일 (`strategies/*.py`)
- `NAME` · `DESCRIPTION` · `REBALANCE`(daily · weekly · monthly · 2weeks · 3weeks · 10days 등)와 `decide(market)`를 둡니다. `decide`는 `{종목코드: 비중}`, 종목코드 목록, `{}`(전부 현금), `KEEP`(그대로 둠) 중 하나를 돌려줍니다.
- 고를 수 있는 종목은 그날의 투자 대상(`market.tradable()`)뿐입니다.
- 이미 아는 결과로 고르지 않습니다: 종목코드 · 종목 이름 · 업종 이름 · 날짜 · 연도를 코드에 직접 적지 않고, `market.name()`으로 고르지 않습니다. 업종(`market.sector()`)은 분산에만 씁니다. backtest · submit이 자동으로 점검합니다.
- 연구는 연구 기간(설정 `research_end`)까지의 데이터로만 합니다. 모의투자 기간 결과는 `kit submit`으로만 계산합니다.
- 파일 · 인터넷 접근, 허용되지 않은 import(pandas · numpy · math · statistics · datetime · functools · itertools · collections · typing · dataclasses · kit.helpers 외), `_`로 시작하는 속성, 시드 없는 무작위는 쓰지 않습니다. `kit.connectors`도 전략 파일에서는 쓰지 않습니다.
- 자세한 내용: `docs/strategy-guide.md`, 백테스트 규칙: `docs/rules.md`

## 연구 (`research/`)
- 외부 연동: `kit.connectors` (`docs/connectors.md`), 연구 도구: `kit.lab` (`docs/research-guide.md`)
- 외부 자료는 '알 수 있게 된 시각' 기준으로 붙입니다 (공시 · 수급 · 거시 지표 · 해외 지수의 시차는 `docs/research-guide.md`).
- 결과 파일은 `research/outputs/`에 저장합니다. `data/`에는 저장하지 않습니다.

## 결과
- 백테스트 결과는 `outputs/<전략 파일 이름>/`에 결과 CSV 양식(`docs/result-spec.md`)으로 저장됩니다. 결과 파일은 읽기만 하고 고치지 않습니다.
- 모의투자 기간 결과 CSV: `uv run kit submit strategies/<파일>.py --name <이름> --team <팀 이름>`
