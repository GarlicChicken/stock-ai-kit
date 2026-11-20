"""결과 규격 (stock-ai-kit result 1).

모든 결과는 같은 양식의 CSV로 나온다. 자세한 설명: docs/result-spec.md

result.csv   날짜별 평가금액 (멤버가 진행자에게 보내는 파일. 레이스는 이 파일로 재생한다)
weights.csv  리밸런싱한 날의 목표 비중 (백테스트 폴더에 참고용으로 저장)
trades.csv   거래 내역 (참고용)
meta.json    이름 · 전략 · 기간 · 요약 지표 (참고용)
"""

import io
import json
from pathlib import Path

import pandas as pd

from .console import KitError
from .helpers import KEEP

SPEC = "stock-ai-kit-result/1"
RESULT_COLUMNS = ["date", "name", "strategy", "equity", "cash", "stock_value", "return", "drawdown", "positions"]
WEIGHT_COLUMNS = ["date", "code", "name", "weight"]
TRADE_COLUMNS = ["date", "code", "name", "side", "qty", "price", "amount", "fee", "tax"]


# ---------------------------------------------------------------- 쓰기

def _csv_bytes(df, float_format=None):
    return df.to_csv(index=False, lineterminator="\n", float_format=float_format).encode("utf-8-sig")


def _dates(df):
    df = df.copy()
    if len(df):
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def result_frame(result, person=""):
    eq = result.equity
    out = pd.DataFrame({
        "date": eq["date"],
        "name": person or "",
        "strategy": result.strategy.name,
        "equity": eq["equity"].astype("int64"),
        "cash": eq["cash"].astype("int64"),
        "stock_value": eq["stock_value"].astype("int64"),
        "return": eq["return"].round(6),
        "drawdown": eq["drawdown"].round(6),
        "positions": eq["positions"].astype("int64"),
    })
    return _dates(out)


def files_for(result, person="", extra_meta=None):
    """결과 규격 파일들의 내용 {파일 이름: bytes}."""
    weights = _dates(result.weights)[WEIGHT_COLUMNS]
    trades = _dates(result.trades)[TRADE_COLUMNS].copy()
    trades["price"] = trades["price"].astype("float64").round(4)
    meta = {
        "spec": SPEC,
        "name": person or "",
        "strategy": result.strategy.name,
        "description": result.strategy.description,
        "rebalance": result.strategy.rebalance,
        "start": result.summary.get("start"),
        "end": result.summary.get("end"),
        "initial_cash": result.summary.get("initial_cash"),
        "summary": {k: result.summary.get(k) for k in
                    ("final_equity", "total_return", "cagr", "mdd", "volatility", "sharpe", "trades", "fees", "taxes", "turnover")},
        "notes": result.notes,
    }
    meta.update(extra_meta or {})
    return {
        "result.csv": _csv_bytes(result_frame(result, person), float_format="%.6f"),
        "weights.csv": _csv_bytes(weights, float_format="%.6f"),
        "trades.csv": _csv_bytes(trades),
        "meta.json": json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
    }


def write_files(out_dir, files):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, b in files.items():
        (out_dir / name).write_bytes(b)


# ---------------------------------------------------------------- 읽기

def _read_csv_bytes(b):
    return pd.read_csv(io.BytesIO(b), encoding="utf-8-sig", dtype={"code": str, "name": str, "strategy": str})


def read_submission(path):
    """결과 CSV 하나를 읽는다. path: result 규격 CSV 파일 (또는 result.csv가 든 결과 폴더)."""
    path = Path(path)
    if path.is_dir():
        path = path / "result.csv"
    if not path.exists() or path.suffix.lower() != ".csv":
        raise KitError(f"{path.name}: 결과 CSV 파일이 아닙니다.")
    r = _read_csv_bytes(path.read_bytes())
    name = str(r["name"].dropna().iloc[0]) if "name" in r and r["name"].notna().any() else path.stem
    strategy = str(r["strategy"].dropna().iloc[0]) if "strategy" in r and r["strategy"].notna().any() else ""
    return {"path": path, "result": r, "name": name, "strategy": strategy}


# ---------------------------------------------------------------- 점검

def validate(result_df, meta=None, calendar=None, start=None, end=None, initial_cash=None):
    """결과 CSV가 규격에 맞는지 본다. (오류 목록, 주의 목록)을 돌려준다.

    calendar: 거래일 목록(있으면 빠진 날짜를 확인), start · end: 진행자가 정한 기간(있으면 기간을 확인)
    """
    errors, warns = [], []
    df = result_df
    missing = [c for c in RESULT_COLUMNS if c not in df.columns]
    if missing:
        return [f"열이 없습니다: {', '.join(missing)} (필요한 열: {', '.join(RESULT_COLUMNS)})"], warns
    if list(df.columns[: len(RESULT_COLUMNS)]) != RESULT_COLUMNS:
        warns.append("열 순서가 규격과 다릅니다 (읽는 데는 문제없음).")
    if len(df) < 2:
        return ["줄이 2개 이상이어야 합니다."], warns
    try:
        dates = pd.to_datetime(df["date"], format="%Y-%m-%d")
    except (ValueError, TypeError):
        return ["date는 YYYY-MM-DD 형식이어야 합니다."], warns
    if not dates.is_monotonic_increasing or dates.duplicated().any():
        errors.append("날짜는 겹치지 않게 오름차순이어야 합니다.")
    for col in ("name", "strategy"):
        vals = df[col].dropna().astype(str).str.strip()
        if vals.empty or (vals == "").all():
            errors.append(f"{col} 칸이 비어 있습니다.")
        elif vals.nunique() > 1:
            errors.append(f"{col} 값은 한 파일 안에서 하나여야 합니다.")
    num = {c: pd.to_numeric(df[c], errors="coerce") for c in ("equity", "cash", "stock_value", "return", "drawdown", "positions")}
    for c, s in num.items():
        if s.isna().any():
            errors.append(f"{c}에 숫자가 아닌 값이 있습니다.")
    if errors:
        return errors, warns
    eq, cash, stock = num["equity"], num["cash"], num["stock_value"]
    if (cash < 0).any() or (stock < 0).any():
        errors.append("cash · stock_value는 0 이상이어야 합니다.")
    if ((eq - cash - stock).abs() > 1).any():
        errors.append("equity = cash + stock_value 가 맞지 않는 줄이 있습니다.")
    initial = initial_cash or (meta or {}).get("initial_cash") or int(round(eq.iloc[0] / (1 + num["return"].iloc[0])))
    if abs(eq.iloc[0] - initial) > 1:
        warns.append(f"첫날 평가금액({eq.iloc[0]:,.0f})이 시작 금액({initial:,.0f})과 다릅니다.")
    if ((eq / initial - 1 - num["return"]).abs() > 1e-5).any():
        errors.append("return = equity ÷ 시작 금액 - 1 이 맞지 않는 줄이 있습니다.")
    if ((eq / eq.cummax() - 1 - num["drawdown"]).abs() > 1e-5).any():
        errors.append("drawdown = equity ÷ 그때까지 최고 equity - 1 이 맞지 않는 줄이 있습니다.")
    if (num["positions"] < 0).any():
        errors.append("positions는 0 이상이어야 합니다.")
    if start is not None and end is not None and calendar is not None:
        want = pd.DatetimeIndex(calendar)
        want = want[(want >= pd.Timestamp(start)) & (want <= pd.Timestamp(end))]
        got = pd.DatetimeIndex(dates)
        if len(want) and (got[0] != want[0] or got[-1] != want[-1]):
            warns.append(f"기간이 다릅니다: 제출 {got[0].date()} ~ {got[-1].date()}, 정한 기간 {want[0].date()} ~ {want[-1].date()}")
        inside = want[(want >= got[0]) & (want <= got[-1])]
        lost = inside.difference(got)
        if len(lost):
            errors.append(f"빠진 거래일이 {len(lost)}일 있습니다 (예: {lost[0].date()}).")
        extra = got.difference(pd.DatetimeIndex(calendar))
        if len(extra):
            errors.append(f"거래일이 아닌 날짜가 {len(extra)}일 있습니다 (예: {extra[0].date()}).")
    return errors, warns


# ---------------------------------------------------------------- 다시 계산해 대조

class _Replay:
    """weights.csv를 그대로 따라 하는 전략."""

    def __init__(self, weights):
        w = weights.copy()
        w["date"] = pd.to_datetime(w["date"])
        w["code"] = w["code"].fillna("").astype(str)
        self.plan = {}
        for d, g in w.groupby("date"):
            self.plan[d] = {c: float(x) for c, x in zip(g["code"], g["weight"]) if c}

    def decide(self, market):
        return self.plan.get(market.today, KEEP)


def replay(weights, panel, cfg, start, end, name="replay"):
    from .engine import run_backtest
    from .strategy import Strategy

    strategy = Strategy(path=Path("weights.csv"), name=name, description="", rebalance="daily", decide=_Replay(weights).decide)
    return run_backtest(strategy, panel, cfg, start, end)


def compare(submitted, recomputed):
    """두 평가금액 표를 날짜별로 비교한다. (같은지, 설명)"""
    a = submitted.assign(date=pd.to_datetime(submitted["date"])).set_index("date")["equity"].astype("int64")
    b = recomputed.assign(date=pd.to_datetime(recomputed["date"])).set_index("date")["equity"].astype("int64")
    common = a.index.intersection(b.index)
    if len(common) != len(a):
        return False, f"다시 계산한 날짜와 {len(a) - len(common)}일이 맞지 않습니다."
    diff = (a.loc[common] - b.loc[common]).abs()
    if (diff <= 1).all():
        return True, "비중 CSV로 다시 계산한 평가금액과 같습니다."
    d = diff[diff > 1].index[0]
    return False, (f"{d.date()}부터 평가금액이 다릅니다 (제출 {a[d]:,} · 다시 계산 {b[d]:,}). "
                   "데이터 · 키트 버전이 다르거나 결과 CSV가 고쳐졌을 수 있습니다.")

