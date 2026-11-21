"""예시: 영업이익이 해마다 꾸준히 늘어난 종목 찾기 (DART 재무제표)

필요한 키: DART_API_KEY
실행: uv run python research/examples/dart_profit_screen.py --date 2022-12-29 --years 3

- 기준일의 투자 대상(시가총액 상위 200개)에서, 최근 years개 사업연도 영업이익이 매년 늘어난 종목을 고른다.
- 기준일까지 '공시된' 사업보고서만 쓴다 (available_date <= 기준일). 3월 결산 공시 전이면 전년도까지 본다.
- 다중회사 API로 100개씩 묶어 해마다 호출한다 (200개 × 4년 = 8번 호출).
"""

import argparse
from pathlib import Path

import pandas as pd

from kit import data
from kit.config import load_config
from kit.connectors import dart

ap = argparse.ArgumentParser()
ap.add_argument("--date", default="2022-12-29")
ap.add_argument("--years", type=int, default=3, help="연속 증가를 볼 해 수")
ap.add_argument("--limit", type=int, default=200, help="시가총액 상위 몇 개까지 볼지")
args = ap.parse_args()

cfg = load_config()
panel = data.load_panel(cfg)
day = pd.Timestamp(args.date)
i = int(panel.dates.searchsorted(day, side="right")) - 1
members = [c for c, m in zip(panel.codes, panel.member.iloc[i]) if m]
marcap = panel.marcap.iloc[i][members].sort_values(ascending=False)
codes = marcap.index[: args.limit].tolist()

last_year = day.year - 1
years = list(range(last_year - args.years, last_year + 1))
# 여러 회사를 해마다 한 번에 묻는다 (100개씩 묶음)
frames = [dart.key_accounts_many(codes, y) for y in years]
acc = pd.concat(frames, ignore_index=True)
acc = acc[acc["available_date"] <= day].dropna(subset=["영업이익"])  # 기준일까지 공시된 것만
rows = []
for code, g in acc.groupby("code"):
    g = g.sort_values("year")
    if len(g) < args.years + 1:
        continue
    op = g["영업이익"].tail(args.years + 1).to_list()
    rising = all(b > a for a, b in zip(op, op[1:]))
    rows.append({"code": code, "name": panel.name_on(code, day), "rising": rising,
                 **{f"영업이익_{y}": v for y, v in zip(g["year"].tail(args.years + 1), op)}})

out = Path("research/outputs")
out.mkdir(parents=True, exist_ok=True)
table = pd.DataFrame(rows)
table.to_csv(out / f"profit_screen_{day:%Y%m%d}.csv", index=False, encoding="utf-8-sig")
picked = table[table["rising"]] if len(table) else table
print(f"\n{day.date()} 기준, {args.years}년 연속 영업이익 증가: {len(picked)}개 / 확인 {len(table)}개")
if len(picked):
    print(picked[["code", "name"]].to_string(index=False))
print(f"전체 표: {out / f'profit_screen_{day:%Y%m%d}.csv'}")
