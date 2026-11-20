"""결과 파일 저장 (CSV · JSON · HTML)."""

import json
from pathlib import Path

import pandas as pd

from .metrics import LABELS
from .paths import ROOT


def _date_str(df):
    df = df.copy()
    if "date" in df.columns and len(df):
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def render_html(payload, path):
    template = (ROOT / "race.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(template.replace("/*__DATA__*/null", data), encoding="utf-8")


def benchmark_series(index_table, dates, initial_cash):
    """지수를 시작 금액 기준 자산 곡선으로 바꾼다."""
    out = []
    if index_table is None or index_table.empty:
        return out
    table = index_table.reindex(pd.DatetimeIndex(dates))
    for name in ("KOSPI", "KOSDAQ"):
        if name not in table.columns:
            continue
        s = table[name]
        first = s.dropna()
        if first.empty:
            continue
        base = first.iloc[0]
        values = [None if pd.isna(v) else round(float(v) / base * initial_cash) for v in s]
        out.append({"name": "코스피" if name == "KOSPI" else "코스닥", "values": values})
    return out


def save_result(result, out_dir, index_table=None, title=None, person="", extra_meta=None):
    """결과 규격 파일(result.csv · weights.csv · trades.csv · meta.json)과 report.html을 저장한다."""
    from . import result as spec

    out_dir = Path(out_dir)
    files = spec.files_for(result, person, extra_meta)
    spec.write_files(out_dir, files)
    s = result.summary
    dates = result.equity["date"]
    initial = s.get("initial_cash")
    trades = _date_str(result.trades.tail(30).iloc[::-1])
    payload = {
        "mode": "report",
        "title": title or result.strategy.name,
        "subtitle": f"{s.get('start')} ~ {s.get('end')} · {result.strategy.description}",
        "initial": initial,
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "series": [{"name": result.strategy.name, "values": result.equity["equity"].astype(int).tolist()}],
        "benchmarks": benchmark_series(index_table, dates, initial),
        "metrics": [{"label": LABELS[k], "key": k, "value": s.get(k)} for k in LABELS],
        "trades": trades[["date", "name", "side", "qty", "price", "amount"]].values.tolist() if len(trades) else [],
    }
    render_html(payload, out_dir / "report.html")
    return files
