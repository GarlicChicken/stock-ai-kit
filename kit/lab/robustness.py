"""우연이 아닌지 확인하는 검사.

좋아 보이는 결과의 대부분은 우연이거나, 여러 번 시도한 것 중 하나만 고른 결과다.
- placebo: 신호를 종목끼리 무작위로 섞어도 비슷한 결과가 나오면 진짜가 아니다.
- halves · yearly: 앞 · 뒤 절반, 해마다 부호가 같은지 본다.
- bootstrap_ci: 날짜 묶음째 다시 뽑아 평균의 신뢰구간을 본다 (0을 포함하면 확실하지 않다).
- bh_adjust: 여러 신호를 한꺼번에 시험했으면 p값을 보정한다 (Benjamini-Hochberg).
무작위를 쓰는 검사는 seed로 고정해 다시 돌려도 같은 결과가 나온다.
"""

import numpy as np
import pandas as pd

from .factor_test import test


def placebo(signal, panel, horizon=5, n=50, seed=42, start=None, end=None):
    """신호를 날짜마다 종목끼리 섞어 n번 검증한다. 진짜 IC보다 큰 경우의 비율(p값)을 돌려준다."""
    real = test(signal, panel, horizon, start=start, end=end)["summary"]["ic_mean"]
    rng = np.random.default_rng(seed)
    values = signal.to_numpy(copy=True)
    fake = []
    for _ in range(n):
        shuffled = np.apply_along_axis(rng.permutation, 1, values)
        df = pd.DataFrame(shuffled, index=signal.index, columns=signal.columns)
        fake.append(test(df, panel, horizon, start=start, end=end)["summary"]["ic_mean"])
    fake = np.array(fake)
    p = float((np.abs(fake) >= abs(real)).mean())
    return {"ic_real": real, "ic_placebo_mean": round(float(fake.mean()), 4),
            "ic_placebo_95": round(float(np.quantile(np.abs(fake), 0.95)), 4), "p_value": round(p, 3), "n": n}


def halves(result):
    """IC를 앞 · 뒤 절반으로 나눈 평균."""
    ic = result["ic"]
    mid = len(ic) // 2
    return {"first_half": round(float(ic.iloc[:mid].mean()), 4), "second_half": round(float(ic.iloc[mid:].mean()), 4)}


def bootstrap_ci(series, block=20, n=1000, seed=42, level=0.95):
    """날짜 묶음(block일)째 다시 뽑아 평균의 신뢰구간."""
    x = pd.Series(series).dropna().to_numpy()
    if len(x) < block * 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(x) / block))
    means = []
    for _ in range(n):
        starts = rng.integers(0, len(x) - block + 1, nb)
        sample = np.concatenate([x[s:s + block] for s in starts])[: len(x)]
        means.append(sample.mean())
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return (round(float(lo), 5), round(float(hi), 5))


def bh_adjust(pvalues):
    """Benjamini-Hochberg로 보정한 p값 (입력 순서 그대로)."""
    p = np.asarray(pvalues, dtype="float64")
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(adj, 1.0)
    return out.round(4).tolist()


def report(signal, panel, horizon=5, start=None, end=None, placebo_n=30, seed=42):
    """검증 + 우연 검사를 한 번에."""
    res = test(signal, panel, horizon, start=start, end=end)
    res["robust"] = {
        "halves": halves(res),
        "ic_ci_95": bootstrap_ci(res["ic"], block=max(horizon, 5) * 4, seed=seed),
        "placebo": placebo(signal, panel, horizon, n=placebo_n, seed=seed, start=start, end=end) if placebo_n else None,
    }
    return res
