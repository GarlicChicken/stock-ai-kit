"""예시: 자기주식 취득 결정 공시가 나온 뒤 주가는 어떻게 움직였나 (DART + 이벤트 스터디)

필요한 키: DART_API_KEY
실행: uv run python research/examples/dart_buyback_event.py --start 2019-01-01 --end 2022-12-31

1) DART 주요사항보고(B) 공시에서 '자기주식취득결정'만 골라 이벤트 표를 만든다.
2) 공시 접수일 장 마감 뒤에 알았다고 보고, 다음 거래일 시가에 산다고 가정해 10거래일 누적 초과수익을 본다.
   (초과수익 = 그날 투자 대상 종목 평균 대비. 비용 빼기 전)
"""

import argparse
from pathlib import Path

import pandas as pd

from kit import data
from kit.config import load_config
from kit.connectors import dart
from kit.lab import event_study

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2019-01-01")
ap.add_argument("--end", default="2022-12-31")
ap.add_argument("--keyword", default="자기주식취득결정")
ap.add_argument("--horizon", type=int, default=10)
args = ap.parse_args()

out = Path("research/outputs")
out.mkdir(parents=True, exist_ok=True)
filings = dart.filings(kind="B", start=args.start, end=args.end)
hit = filings[filings["report"].str.contains(args.keyword, regex=False)
              & ~filings["report"].str.contains("정정", regex=False)
              & (filings["stock_code"].str.len() == 6)]
events = hit.rename(columns={"stock_code": "code"})[["date", "code", "corp_name", "report", "url"]]
events.to_csv(out / "events_buyback.csv", index=False, encoding="utf-8-sig")
print(f"주요사항보고 {len(filings)}건 중 '{args.keyword}' {len(events)}건 -> {out / 'events_buyback.csv'}")

cfg = load_config()
panel = data.load_panel(cfg)
res = event_study.run(events, panel, horizon=args.horizon)
s = res["summary"]
print(f"계산된 이벤트 {s['events']}건 (투자 대상 밖 · 데이터 밖 종목 포함 원본 {len(events)}건)")
print(res["curve"].to_string(index=False))
res["curve"].to_csv(out / "event_buyback_curve.csv", index=False, encoding="utf-8-sig")
