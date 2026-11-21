"""config/kit.toml 읽기."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .console import KitError
from .paths import CONFIG


@dataclass(frozen=True)
class Config:
    data_start: pd.Timestamp
    data_end: pd.Timestamp
    research_end: pd.Timestamp
    research_lock: bool
    compare_start: pd.Timestamp
    compare_end: pd.Timestamp
    top_n: int
    adjust_anchor: pd.Timestamp
    initial_cash: int
    cash_buffer: float
    commission: float
    slippage: float
    sell_tax: dict = field(default_factory=dict)  # {"KOSPI": [(시작일, 세율), ...]}

    def tax_rate(self, market, date):
        table = self.sell_tax.get(market) or self.sell_tax.get("KOSPI") or []
        rate = table[0][1] if table else 0.0  # 표의 첫 날짜보다 이전이면 첫 세율
        for start, value in table:
            if date >= start:
                rate = value
        return rate


def _tax_table(raw):
    out = {}
    for market, rows in (raw or {}).items():
        out[market] = sorted((pd.Timestamp(k), float(v)) for k, v in rows.items())
    return out


def load_config(path=None):
    path = Path(path) if path else CONFIG / "kit.toml"
    if not path.exists():
        raise KitError(f"설정 파일이 없습니다: {path}")
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    data = raw.get("data", {})
    period = raw.get("period", {})
    account = raw.get("account", {})
    cost = raw.get("cost", {})
    research_end = pd.Timestamp(period.get("research_end", "2024-12-31"))
    return Config(
        data_start=pd.Timestamp(period.get("data_start", "2000-01-01")),
        data_end=pd.Timestamp(period.get("data_end", research_end)),
        research_end=research_end,
        research_lock=bool(period.get("research_lock", False)),
        compare_start=pd.Timestamp(period.get("compare_start", "2025-01-02")),
        compare_end=pd.Timestamp(period.get("compare_end", "2026-10-30")),
        top_n=int(data.get("top_n", 200)),
        adjust_anchor=pd.Timestamp(data.get("adjust_anchor", research_end)),
        initial_cash=int(account.get("initial_cash", 10_000_000)),
        cash_buffer=float(account.get("cash_buffer", 0.002)),
        commission=float(cost.get("commission", 0.00015)),
        slippage=float(cost.get("slippage", 0.0)),
        sell_tax=_tax_table(cost.get("sell_tax")),
    )
