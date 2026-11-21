"""진행자용: 멤버들이 보낸 결과 CSV를 모아 수익 레이스 화면을 만든다.

명령 없이 보려면 키트 폴더의 race.html을 브라우저로 열고 CSV를 끌어다 놓아도 된다.
이 명령은 같은 화면에 코스피 · 코스닥 비교선을 넣고, 규격에 맞지 않는 CSV를 이유와 함께 알려 준다.
"""

import math
from pathlib import Path

import pandas as pd

from . import result as spec
from .console import KitError, fail, ok, pct, warn
from .paths import OUTPUTS
from .report import benchmark_series, render_html


def team_table(rows, curves, initial):
    """팀별 성적: 팀원 평가금액 곡선의 평균 (= 팀원 수익률의 평균). 팀 이름이 있는 결과만.

    curves: {이름: 같은 출발선으로 맞춘 날짜별 평가금액 Series}
    """
    teams = {}
    for r in rows:
        if r.get("팀"):
            teams.setdefault(r["팀"], []).append(r["이름"])
    out = []
    for team, names in teams.items():
        avg = pd.concat([curves[n] for n in names], axis=1).mean(axis=1)
        out.append({"팀": team, "인원": len(names), "팀원": " · ".join(names),
                    "평균 평가금액": int(math.floor(avg.iloc[-1] + 0.5)), "평균 수익률": round(float(avg.iloc[-1] / initial - 1), 6),
                    "최대 낙폭": round(float((avg / avg.cummax() - 1).min()), 6)})
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out).sort_values("평균 평가금액", ascending=False).reset_index(drop=True)
    df.insert(0, "순위", range(1, len(df) + 1))
    return df


def find_csvs(folder):
    folder = Path(folder)
    return sorted(p for p in folder.glob("*.csv") if not p.name.startswith((".", "_")))


def run_race(folder, cfg, calendar, index_table, start=None, end=None):
    files = find_csvs(folder)
    if not files:
        raise KitError(f"{folder} 안에 결과 CSV가 없습니다.")
    subs = []
    for p in files:
        try:
            sub = spec.read_submission(p)
        except Exception as e:
            fail(f"{p.name}: 읽지 못해 뺐습니다 ({e})")
            continue
        errors, warns = spec.validate(sub["result"], None, calendar, start, end, cfg.initial_cash)
        if errors:
            fail(f"{p.name}: 결과 CSV 양식에 맞지 않아 뺐습니다")
            for e in errors[:4]:
                print(f"    {e}")
            continue
        for w in warns:
            warn(f"{p.name}: {w}")
        sub["result"]["date"] = pd.to_datetime(sub["result"]["date"])
        subs.append(sub)
    if not subs:
        raise KitError("양식에 맞는 결과 CSV가 없습니다.")

    lo = max(s["result"]["date"].iloc[0] for s in subs)
    hi = min(s["result"]["date"].iloc[-1] for s in subs)
    if start is not None:
        lo = max(lo, pd.Timestamp(start))
    if end is not None:
        hi = min(hi, pd.Timestamp(end))
    if lo >= hi:
        raise KitError("CSV들의 기간이 겹치지 않습니다.")
    if any(s["result"]["date"].iloc[0] != lo or s["result"]["date"].iloc[-1] != hi for s in subs):
        warn(f"CSV마다 기간이 달라 겹치는 기간({lo.date()} ~ {hi.date()})으로 맞춥니다.")

    seen = {}
    for sub in subs:  # 같은 이름이 둘 이상이면 (2), (3)을 붙인다
        n = seen.get(sub["name"], 0) + 1
        seen[sub["name"]] = n
        if n > 1:
            sub["name"] = f"{sub['name']} ({n})"

    dates = pd.DatetimeIndex(sorted(set().union(*[set(s["result"]["date"]) for s in subs])))
    dates = dates[(dates >= lo) & (dates <= hi)]
    out_root = OUTPUTS / "race"
    out_root.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame({"date": dates.strftime("%Y-%m-%d")})
    series, rows, curves = [], [], {}
    initial = cfg.initial_cash
    rebased = False
    for sub in subs:
        eq = sub["result"].set_index("date")["equity"].astype("float64").reindex(dates).ffill().bfill()
        if abs(eq.iloc[0] - initial) > 1:  # 같은 출발선: 시작일 평가금액을 시작 금액으로 맞춘다
            eq = eq / eq.iloc[0] * initial
            rebased = True
        eq = eq.round()
        curves[sub["name"]] = eq
        values = eq.astype("int64").tolist()
        table[sub["name"]] = values
        series.append({"name": sub["name"], "label": sub["strategy"], "team": sub.get("team", ""), "values": values})
        first, final = initial, values[-1]
        rows.append({"이름": sub["name"], "팀": sub.get("team", ""), "전략": sub["strategy"], "최종 평가금액": final,
                     "총수익률": round(final / first - 1, 6), "최대 낙폭": round(float((eq / eq.cummax() - 1).min()), 6),
                     "파일": sub["path"].name})
        ok(f"{sub['name']} · {sub['strategy']} : {pct(final / first - 1)}")
    if rebased:
        warn(f"같은 출발선에서 비교하도록 {dates[0].date()} 평가금액을 모두 {initial:,}원으로 다시 맞췄습니다 (수익률 흐름은 그대로).")
    rows.sort(key=lambda r: r["최종 평가금액"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["순위"] = i
    pd.DataFrame(rows)[["순위", "이름", "팀", "전략", "최종 평가금액", "총수익률", "최대 낙폭", "파일"]] \
        .to_csv(out_root / "leaderboard.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    teams = team_table(rows, curves, initial)
    if len(teams):
        teams.to_csv(out_root / "team_leaderboard.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    table.to_csv(out_root / "race_equity.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    payload = {
        "mode": "race",
        "title": "수익 레이스",
        "subtitle": f"{dates[0].date()} ~ {dates[-1].date()} · 시작 금액 {initial:,}원 · {len(series)}명",
        "initial": initial,
        "dates": table["date"].tolist(),
        "series": series,
        "benchmarks": benchmark_series(index_table, dates, initial) if index_table is not None else [],
    }
    render_html(payload, out_root / "race.html")
    return out_root / "race.html", rows, teams
