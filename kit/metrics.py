"""성과 지표."""

import math

import numpy as np


def summarize(equity, trades, initial_cash):
    """equity: date, equity 열이 있는 표. trades: 거래 내역 표."""
    eq = equity["equity"].astype("float64").to_numpy()
    dates = equity["date"]
    if len(eq) == 0:
        return {}
    daily = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])
    years = max((dates.iloc[-1] - dates.iloc[0]).days / 365.25, 1e-9)
    final = float(eq[-1])
    total = final / initial_cash - 1
    cagr = (final / initial_cash) ** (1 / years) - 1 if final > 0 and years > 0.05 else float("nan")
    peak = np.maximum.accumulate(eq)
    mdd = float(np.min(eq / peak - 1))
    std = float(np.std(daily)) if len(daily) else 0.0
    vol = std * math.sqrt(252)
    sharpe = float(np.mean(daily)) / std * math.sqrt(252) if std > 0 else float("nan")
    traded = float(trades["amount"].sum()) if len(trades) else 0.0
    return {
        "start": dates.iloc[0].strftime("%Y-%m-%d"),
        "end": dates.iloc[-1].strftime("%Y-%m-%d"),
        "days": int(len(eq)),
        "initial_cash": int(initial_cash),
        "final_equity": int(round(final)),
        "total_return": round(total, 6),
        "cagr": round(cagr, 6) if cagr == cagr else None,
        "mdd": round(mdd, 6),
        "volatility": round(vol, 6),
        "sharpe": round(sharpe, 4) if sharpe == sharpe else None,
        "trades": int(len(trades)),
        "fees": int(trades["fee"].sum()) if len(trades) else 0,
        "taxes": int(trades["tax"].sum()) if len(trades) else 0,
        "turnover": round(traded / float(np.mean(eq)) / years, 4) if years > 0 else None,
    }


LABELS = {
    "final_equity": "최종 자산",
    "total_return": "총수익률",
    "cagr": "연평균 수익률",
    "mdd": "최대 낙폭",
    "volatility": "변동성(연)",
    "sharpe": "샤프 지수",
    "trades": "거래 수",
    "turnover": "회전율(연)",
}
