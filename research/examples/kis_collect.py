"""예시: 증권사 API로 오늘 분봉 · 최근 투자자별 매매동향을 받아 쌓기 (한국투자증권, 조회만)

필요한 키: KIS_APP_KEY · KIS_APP_SECRET (KIS_ENV=mock 모의투자 기본)
실행: uv run python research/examples/kis_collect.py --codes 005930,000660

- 분봉은 무료로 오래 보관되지 않으므로 장이 끝난 뒤 매일 실행해 data/minute/ 아래 CSV에 이어 붙인다.
- 투자자별 매매동향(개인 · 외국인 · 기관 순매수)은 장 마감 뒤 공표된다. 오늘 행은 장 마감 뒤에만 채워진다.
  공표 시차 때문에 수급 신호는 다음 거래일 결정에만 쓴다.
- 토큰은 앱키당 1분에 1번만 발급된다. 받은 토큰은 .cache에 저장해 다시 쓴다.
"""

import argparse
from pathlib import Path

import pandas as pd

from kit.connectors import kis

ap = argparse.ArgumentParser()
ap.add_argument("--codes", default="005930,000660")
args = ap.parse_args()

minute_dir = Path("data/minute")
flow_dir = Path("research/outputs")
minute_dir.mkdir(parents=True, exist_ok=True)
flow_dir.mkdir(parents=True, exist_ok=True)
for code in [c.strip().zfill(6) for c in args.codes.split(",") if c.strip()]:
    bars = kis.minutes_today(code)
    path = minute_dir / f"{code}_kis_1m.csv"
    if path.exists():
        bars = pd.concat([pd.read_csv(path, dtype={"code": str}, parse_dates=["datetime"]), bars])
    bars = bars.drop_duplicates("datetime", keep="last").sort_values("datetime")
    bars.to_csv(path, index=False)
    flows = kis.investor_flows(code)
    flows.to_csv(flow_dir / f"flows_{code}.csv", index=False, encoding="utf-8-sig")
    print(f"{code}: 분봉 {len(bars)}줄 -> {path} · 수급 {len(flows)}일 -> {flow_dir / f'flows_{code}.csv'}")
