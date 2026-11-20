"""예시: 국내 거시 지표(ECOS)와 해외 지표를 코스피와 같은 날짜 축으로 모으기

필요한 키: ECOS_API_KEY (없으면 시험용 키로 10건만), 해외 지표는 필요 없음
실행: uv run python research/examples/macro_dashboard.py --start 2020-01-01

시점 맞추기 (미래 데이터를 쓰지 않게)
- 일간 금리 · 환율(ECOS): 그날 값. 한국 장 마감 뒤 결정이면 그날 값까지 쓸 수 있다고 본다.
- 월간 지표(물가): 다음 달에 발표되므로 한 달 늦춰 붙인다.
- 미국 지수(yfinance): 한국 t일 결정에는 미국 t-1일 종가까지.
"""

import argparse
from pathlib import Path

import pandas as pd

from kit import data
from kit.config import load_config
from kit.connectors import ecos, world

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2020-01-01")
args = ap.parse_args()
start = pd.Timestamp(args.start)

cfg = load_config()
panel = data.load_panel(cfg)
days = panel.dates[panel.dates >= start]
table = pd.DataFrame(index=days)
idx = data.load_index(days)
if "KOSPI" in idx:
    table["코스피"] = idx["KOSPI"]

for name in ("기준금리", "국고채3년", "원달러환율"):
    s = ecos.get(name, start.strftime("%Y%m%d"), days[-1].strftime("%Y%m%d"))
    table[name] = s.set_index("date")["value"].reindex(days, method="ffill")
cpi = ecos.get("소비자물가", start.strftime("%Y%m"), days[-1].strftime("%Y%m"))
cpi_yoy = cpi.set_index("date")["value"].pct_change(12, fill_method=None) * 100
cpi_yoy.index = cpi_yoy.index + pd.offsets.MonthBegin(1)  # 발표 시차: 한 달 늦춰 붙인다
table["물가상승률(%)"] = cpi_yoy.reindex(days, method="ffill")

spx = world.prices("^GSPC", start=(start - pd.Timedelta(days=10)).strftime("%Y-%m-%d")).set_index("date")["close"]
spx_ret = spx.pct_change(fill_method=None)
prev = days - pd.Timedelta(days=1)  # 한국 t일 결정에는 미국 t-1일(이전) 종가까지
table["미국 S&P500 전일 수익률"] = spx_ret.reindex(spx_ret.index.union(prev)).ffill().reindex(prev).to_numpy()

out = Path("research/outputs")
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / "macro_dashboard.csv", encoding="utf-8-sig")
print(table.tail(5).round(3).to_string())
print(f"\n저장: {out / 'macro_dashboard.csv'} ({len(table)}일)")
