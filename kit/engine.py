"""백테스트 엔진.

규칙 (자세한 설명: docs/rules.md)
- 리밸런싱하는 날 장 마감 뒤 decide(market)를 부르고, 그 결과대로 다음 거래일 시가에 사고판다.
- 새로 살 수 있는 종목은 그날의 투자 대상(지난달 말 시가총액 상위 N종목)뿐이다.
- 1주 단위로 거래한다(수정주가 기준). 수수료는 살 때·팔 때, 증권거래세는 팔 때 낸다 (원 미만 버림).
- 그날 거래가 없던 종목(거래정지 등)은 사고팔 수 없고 들고 있던 수량을 그대로 둔다.
- 들고 있던 종목이 상장폐지되면 마지막 거래일 종가로 정리한다(세금 · 수수료 포함).
- 공매도·신용(빚) 없이 현금 안에서만 산다. 비중 합이 1을 넘으면 1로 줄인다.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .console import KitError
from .helpers import KEEP
from .market import Market
from .metrics import summarize
from .strategy import parse_rebalance


@dataclass
class Result:
    strategy: object
    equity: pd.DataFrame
    trades: pd.DataFrame
    weights: pd.DataFrame
    summary: dict
    notes: list


_EPOCH_MONDAY = pd.Timestamp("2000-01-03")


def _period_no(ts, unit):
    """달력에 고정된 기간 번호 (시작일과 상관없이 같은 날에 리밸런싱하도록)."""
    if unit == "week":
        return (ts - pd.Timedelta(days=ts.weekday()) - _EPOCH_MONDAY).days // 7
    if unit == "month":
        return ts.year * 12 + ts.month - 1
    return None


def decision_days(dates, s, e, rebalance):
    """s~e 구간에서 decide를 부를 날.

    첫날은 늘 부르고, 그 뒤로는 주 · 달 단위면 N번째 주 · 달의 마지막 거래일, 거래일 단위면 N거래일마다.
    기간 번호를 달력에 고정해 두어 시작일이 달라도 같은 날에 결정한다.
    """
    unit, n = parse_rebalance(rebalance)
    days = np.zeros(e - s + 1, dtype=bool)
    for i in range(s, e + 1):
        if i == s:
            days[i - s] = True
        elif unit == "day":
            days[i - s] = i % n == 0
        else:
            p = _period_no(dates[i], unit)
            last = i + 1 >= len(dates) or _period_no(dates[i + 1], unit) != p
            days[i - s] = last and p % n == n - 1
    return days


def normalize_weights(raw, col, member_row, notes):
    """decide()가 돌려준 값을 {종목코드: 비중}으로 정리한다."""
    if raw is None:
        return {}
    if isinstance(raw, pd.Series):
        raw = raw.to_dict()
    elif isinstance(raw, (list, tuple, set, pd.Index)):
        items = list(raw)
        raw = {c: 1.0 / len(items) for c in items} if items else {}
    if not isinstance(raw, dict):
        raise KitError("decide()는 {종목코드: 비중} 사전이나 종목코드 목록을 돌려줘야 합니다.")
    out = {}
    for code, w in raw.items():
        code = str(code)
        if code.isdigit():
            code = code.zfill(6)
        if code not in col:
            notes.append(f"데이터에 없는 종목코드 무시: {code}")
            continue
        if not member_row[col[code]]:
            notes.append(f"그날 투자 대상(시가총액 상위)이 아닌 종목 무시: {code}")
            continue
        try:
            w = float(w)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(w) or w <= 0:
            continue
        out[code] = out.get(code, 0.0) + w
    total = sum(out.values())
    if total > 1.0 + 1e-9:
        out = {c: w / total for c, w in out.items()}
    return out


def run_backtest(strategy, panel, cfg, start=None, end=None):
    dates = panel.dates
    if len(dates) == 0:
        raise KitError("데이터가 비어 있습니다.")
    s = int(dates.searchsorted(pd.Timestamp(start))) if start is not None else 0
    e = int(dates.searchsorted(pd.Timestamp(end), side="right")) - 1 if end is not None else len(dates) - 1
    if s > e or s >= len(dates):
        raise KitError(f"기간 안에 거래일이 없습니다 ({start} ~ {end}). 데이터 기간: {dates[0].date()} ~ {dates[-1].date()}")

    codes = panel.codes
    n = len(codes)
    col = {c: k for k, c in enumerate(codes)}
    open_ = panel.open.to_numpy("float64")
    close = panel.close.to_numpy("float64")
    volume = panel.volume.to_numpy("float64")
    close_ff = panel.close.ffill().to_numpy("float64")
    member = panel.member.to_numpy()
    tradable = np.isfinite(open_) & (open_ > 0) & np.isfinite(volume) & (volume > 0)
    has_close = np.isfinite(close)
    last_idx = np.where(has_close.any(axis=0), len(dates) - 1 - np.argmax(has_close[::-1], axis=0), -1)

    cash = int(cfg.initial_cash)
    shares = np.zeros(n, dtype=np.int64)
    pending = None
    notes = []
    eq_rows, trade_rows, weight_rows = [], [], []
    decide_on = decision_days(dates, s, e, strategy.rebalance)
    slip, fee_rate = cfg.slippage, cfg.commission

    for i in range(s, e + 1):
        day = dates[i]

        # 0) 상장폐지: 데이터가 끝난 종목을 들고 있으면 마지막 종가로 정리
        gone = np.nonzero((shares > 0) & (last_idx < i))[0]
        for k in gone:
            qty = int(shares[k])
            price = close_ff[i, k]
            amount = int(round(qty * price))
            fee = int(math.floor(amount * fee_rate))
            tax = int(math.floor(amount * cfg.tax_rate(panel.market_on(codes[k], dates[last_idx[k]]), dates[last_idx[k]])))
            cash += amount - fee - tax
            shares[k] = 0
            trade_rows.append((day, codes[k], panel.name_on(codes[k], day), "상장폐지 정리", qty, price, amount, fee, tax))

        # 1) 어제 정한 목표 비중대로 오늘 시가에 체결
        if pending is not None:
            ref = np.where(tradable[i], open_[i], close_ff[i - 1] if i > 0 else np.nan)
            held_value = float(np.nansum(np.where(shares > 0, shares * ref, 0.0)))
            investable = (cash + held_value) * (1 - cfg.cash_buffer)
            target = shares.copy()
            target[tradable[i]] = 0  # 거래 가능한 종목은 목표에 없으면 전부 판다
            for code, w in pending.items():
                k = col[code]
                if tradable[i, k]:
                    target[k] = int(math.floor(investable * w / (open_[i, k] * (1 + slip))))
            # 파는 것부터
            for k in np.nonzero(shares > target)[0]:
                qty = int(shares[k] - target[k])
                price = open_[i, k] * (1 - slip)
                amount = int(round(qty * price))
                fee = int(math.floor(amount * fee_rate))
                tax = int(math.floor(amount * cfg.tax_rate(panel.market_on(codes[k], day), day)))
                cash += amount - fee - tax
                shares[k] -= qty
                trade_rows.append((day, codes[k], panel.name_on(codes[k], day), "매도", qty, price, amount, fee, tax))
            # 그다음 사는 것
            for k in np.nonzero(target > shares)[0]:
                qty = int(target[k] - shares[k])
                price = open_[i, k] * (1 + slip)
                amount = int(round(qty * price))
                fee = int(math.floor(amount * fee_rate))
                if amount + fee > cash:
                    qty = int(math.floor(cash / (price * (1 + fee_rate))))
                    if qty <= 0:
                        continue
                    amount = int(round(qty * price))
                    fee = int(math.floor(amount * fee_rate))
                    if amount + fee > cash:
                        continue
                cash -= amount + fee
                shares[k] += qty
                trade_rows.append((day, codes[k], panel.name_on(codes[k], day), "매수", qty, price, amount, fee, 0))
            pending = None

        # 2) 오늘 종가로 평가
        mark = np.where(shares > 0, shares * close_ff[i], 0.0)
        stock_value = int(round(float(np.nansum(mark))))
        equity = cash + stock_value
        eq_rows.append((day, equity, cash, stock_value, int((shares > 0).sum())))

        # 3) 리밸런싱하는 날이면 장 마감 뒤 다음 목표를 정한다 (마지막 날은 체결할 날이 없어 건너뜀)
        if decide_on[i - s] and i < e:
            holdings = {}
            if equity > 0:
                for k in np.nonzero(shares)[0]:
                    holdings[codes[k]] = float(shares[k] * close_ff[i, k] / equity)
            market = Market(panel, i, holdings)
            try:
                raw = strategy.decide(market)
            except KitError:
                raise
            except Exception as ex:
                raise KitError(f"{day.date()} decide()에서 오류: {type(ex).__name__}: {ex}") from ex
            if raw is KEEP:
                continue  # 이번에는 그대로 둔다
            pending = normalize_weights(raw, col, member[i], notes)
            if pending:
                for code in sorted(pending):
                    weight_rows.append((day, code, panel.name_on(code, day), round(pending[code], 6)))
            else:
                weight_rows.append((day, "", "현금", 0.0))

    equity_df = pd.DataFrame(eq_rows, columns=["date", "equity", "cash", "stock_value", "positions"])
    equity_df["return"] = equity_df["equity"] / cfg.initial_cash - 1
    equity_df["drawdown"] = equity_df["equity"] / equity_df["equity"].cummax() - 1
    trades_df = pd.DataFrame(trade_rows, columns=["date", "code", "name", "side", "qty", "price", "amount", "fee", "tax"])
    weights_df = pd.DataFrame(weight_rows, columns=["date", "code", "name", "weight"])
    summary = summarize(equity_df, trades_df, cfg.initial_cash)
    summary.update({"strategy": strategy.name, "rebalance": strategy.rebalance})
    uniq_notes = sorted(set(notes))
    return Result(strategy, equity_df, trades_df, weights_df, summary, uniq_notes)
