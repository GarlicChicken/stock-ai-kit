"""예시: 기본 신호를 한꺼번에 검증하고, 여러 개를 시험한 만큼 p값을 보정해 표로 보기

필요한 키: 없음 (표준 데이터만)
실행: uv run python research/examples/factor_lab.py --start 2016-01-01 --end 2024-12-31 --horizon 5

- 신호마다 IC(신호 순위와 앞으로 수익률 순위의 상관) · 5분위 롱숏 차이 · 해마다 부호를 본다.
- 여러 신호를 한꺼번에 시험하면 그중 몇 개는 우연히 좋아 보인다. Benjamini-Hochberg로 보정한 값도 같이 본다.
- 비용은 빼지 않은 값이다. 쓸 만해 보이면 전략 파일로 만들어 백테스트(비용 포함)로 다시 확인한다.
"""

import argparse
import math
from pathlib import Path

import pandas as pd

from kit import data
from kit.config import load_config
from kit.lab import factor_test, robustness, signals

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2016-01-01")
ap.add_argument("--end", default="2024-12-31")
ap.add_argument("--horizon", type=int, default=5)
args = ap.parse_args()

cfg = load_config()
panel = data.load_panel(cfg)
rows = []
for name, (_, desc) in signals.SIGNALS.items():
    res = factor_test.test(signals.compute(panel, name), panel, args.horizon, start=args.start, end=args.end)
    s = res["summary"]
    p = math.erfc(abs(s["ic_t"]) / math.sqrt(2))  # 정규분포 근사 양측 p값
    rows.append({"신호": name, "설명": desc, "IC": s["ic_mean"], "IC t": s["ic_t"], "롱숏": s["spread_mean"],
                 "롱숏 t": s["spread_t"], "같은 부호 해": f"{s['years_same_sign']}/{s['years']}", "p": round(p, 4)})
    print(f"  {name} 완료")
table = pd.DataFrame(rows)
table["보정 p"] = robustness.bh_adjust(table["p"].tolist())
table = table.sort_values("IC t", key=abs, ascending=False)
print(table.to_string(index=False))
out = Path("research/outputs")
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / "factor_lab.csv", index=False, encoding="utf-8-sig")
print(f"\n저장: {out / 'factor_lab.csv'}")
