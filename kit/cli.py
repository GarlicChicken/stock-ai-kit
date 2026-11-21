"""명령어 모음. 키트 폴더에서 `uv run kit <명령>` 으로 실행한다."""

import argparse
import hashlib
import io
import json
import platform
import re
import shutil
import sys
import time
from importlib import metadata
from pathlib import Path

import pandas as pd

from . import __version__, data, guard, lookahead
from .config import load_config
from .console import KitError, fail, head, ok, pct, setup, warn, won
from .engine import run_backtest
from .paths import OUTPUTS, ROOT, SAMPLE, STRATEGIES, SUBMISSIONS, TEMPLATES
from .report import save_result
from .strategy import load_strategy, rebalance_label

PACKAGES = ["pandas", "numpy", "pyarrow", "finance-datareader", "pykrx", "yfinance"]


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- check

def _sample_run(update=False):
    """가상의 원천 데이터(kit/sample/raw.csv)로 데이터 만들기 · 자르기 · 백테스트를 한 번에 시험한다."""
    cfg = load_config(SAMPLE / "sample.toml")
    raw = pd.read_csv(SAMPLE / "raw.csv", dtype={"Code": str}, parse_dates=["Date"])
    years = sorted(int(y) for y in raw["Date"].dt.year.unique())

    def load(y):
        return raw[raw["Date"].dt.year == y]

    prices, universe, stocks = data.build_dataset(load, years, cfg.data_start, cfg.research_end, cfg.top_n)
    fp = data.fingerprint(data.dataset_bytes(prices, universe, stocks))
    # 중간에서 자른 데이터 = 그 날짜로 새로 만든 데이터인지
    mid = cfg.compare_start - pd.Timedelta(days=1)
    cut = data.fingerprint(data.dataset_bytes(*data.cut_dataset(prices, universe, mid)))
    fresh = data.fingerprint(data.dataset_bytes(*data.build_dataset(load, years, cfg.data_start, mid, cfg.top_n)))
    panel = data.Panel(prices, universe, stocks, cfg.adjust_anchor)
    results = {"data": {"fingerprint": fp, "delisted": int(stocks["delisted"].sum()), "cut_matches": cut == fresh}}
    from . import result as spec

    digest, valid, replays = hashlib.sha256(), True, True
    for f in sorted((SAMPLE / "strategies").glob("*.py")):
        res = run_backtest(load_strategy(f), panel, cfg)
        results[f.stem] = {"final_equity": res.summary["final_equity"], "trades": res.summary["trades"]}
        files = spec.files_for(res, "샘플")
        digest.update(files["result.csv"])
        errors, _ = spec.validate(pd.read_csv(io.BytesIO(files["result.csv"]), encoding="utf-8-sig"),
                                  calendar=panel.dates, start=cfg.data_start, end=cfg.research_end, initial_cash=cfg.initial_cash)
        valid &= not errors
        again = spec.replay(res.weights, panel, cfg, res.equity["date"].iloc[0], res.equity["date"].iloc[-1])
        replays &= spec.compare(res.equity, again.equity)[0]
    results["spec"] = {"result_csv": digest.hexdigest()[:8], "valid": bool(valid), "replay_matches": bool(replays)}
    expected_path = SAMPLE / "expected.json"
    if update:
        expected_path.write_bytes((json.dumps(results, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    return results, expected


def cmd_check(args):
    all_ok = True
    head("1. 실행 환경")
    py = sys.version_info
    if (py.major, py.minor) == (3, 13):
        ok(f"파이썬 {platform.python_version()}")
    else:
        all_ok = False
        fail(f"파이썬 {platform.python_version()} (3.13이어야 합니다. 'uv run kit check'로 실행했는지 확인해 주세요)")
    print(f"     운영체제: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"     키트: {__version__} · 폴더: {ROOT}")
    for name in PACKAGES:
        try:
            print(f"     {name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            all_ok = False
            fail(f"{name} 패키지가 없습니다. 'uv sync --locked'를 다시 실행해 주세요.")

    head("2. 샘플 시험 (어느 PC에서나 같은 숫자가 나와야 합니다)")
    try:
        results, expected = _sample_run(update=args.update_expected)
        for key, got in results.items():
            want = expected.get(key)
            same = want == got
            all_ok &= same
            if key == "spec":
                good = same and got["valid"] and got["replay_matches"]
                all_ok &= good
                (ok if good else fail)(f"결과 CSV      지문 {got['result_csv']} · 양식 점검 통과 · 비중으로 다시 계산 일치")
            elif key == "data":
                good = same and got["cut_matches"]
                all_ok &= good
                (ok if good else fail)(f"데이터 만들기   지문 {got['fingerprint']} · 상장폐지 {got['delisted']}종목 · 기간 자르기 일치")
            else:
                (ok if same else fail)(f"{key:<14} 최종 자산 {won(got['final_equity']):>14} · 거래 {got['trades']}건")
        if set(results) != set(expected):
            all_ok = False
            fail("샘플 전략 목록이 기준과 다릅니다.")
    except Exception as e:
        all_ok = False
        fail(f"샘플 시험 중 오류: {type(e).__name__}: {e}")

    head("3. 데이터 (data 폴더)")
    cfg = load_config()
    print(f"     연구 기간 ~ {cfg.research_end.date()} · 모의투자 기간 {cfg.compare_start.date()} ~ {cfg.compare_end.date()} · "
          f"시작 금액 {won(cfg.initial_cash)}")
    info = data.describe(None)
    if info is None:
        warn("아직 데이터가 없습니다.")
        print("     진행자가 준 데이터 zip이 있으면: uv run kit data unpack <zip 파일 경로>")
        print("     직접 받으려면:                  uv run kit data download")
    else:
        good, detail = data.verify()
        (ok if good else warn)(f"{info['start']} ~ {info['end']} · 매달 시가총액 상위 {info.get('top_n')}종목 · "
                               f"전체 {info['codes']}종목(상장폐지 {info.get('delisted', 0)})")
        print(f"     데이터 지문: {info['fingerprint']}  (진행자 화면의 지문과 같으면 같은 데이터입니다)")
        if not good:
            warn(detail)

    print()
    if all_ok:
        ok("세팅 완료: 샘플 결과가 기준값과 모두 같습니다.")
        return 0
    fail("세팅이 끝나지 않았습니다. 위의 [실패] 줄을 확인해 주세요.")
    return 1


# ---------------------------------------------------------------- sources

def cmd_sources(args):
    from . import sources

    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=20)
    checks = [
        ("marcap 원천 (올해 파일)", lambda: [1] if sources.marcap_available(end.year) else []),
        ("FinanceDataReader 일봉", lambda: sources.get_daily("005930", start, end, source="fdr")),
        ("yfinance 일봉", lambda: sources.get_daily("005930", start, end, source="yahoo", market="KOSPI")),
        ("yfinance 1분봉", lambda: sources.get_minute("005930", "1m", 2, market="KOSPI")),
        ("pykrx 일봉", lambda: sources.get_daily("005930", start, end, source="pykrx")),
        ("FinanceDataReader 종목 목록", lambda: sources.get_listing("KRX")),
        ("FinanceDataReader 코스피 지수", lambda: sources.get_index("KOSPI", start, end)),
    ]
    head("데이터 출처 연결 점검 (삼성전자 005930 기준)")
    bad = 0
    for label, fn in checks:
        t0 = time.time()
        try:
            df = fn()
            n = len(df)
            if n and label.startswith("marcap"):
                ok(f"{label:<28}   열림 ({time.time() - t0:.1f}초)")
            elif n:
                ok(f"{label:<28} {n:>6}줄 ({time.time() - t0:.1f}초)")
            else:
                bad += 1
                fail(f"{label:<28} 받은 데이터 없음")
        except Exception as e:
            bad += 1
            fail(f"{label:<28} {type(e).__name__}: {str(e)[:80]}")
    print("\n출처별 특징과 한계: docs/data-sources.md")
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------- data

def cmd_data(args):
    cfg = load_config()
    folder = Path(args.data) if args.data else None
    where = _rel(folder) if folder else "data"
    if args.action == "download":
        # 기본은 설정의 데이터 끝(data_end)까지. 최신까지 받으려면 --end today
        end = None if (args.end or "").lower() == "today" else (args.end or cfg.data_end)
        t0 = time.time()
        m = data.download(cfg, args.start, end, folder=folder, top_n=args.top, refresh=args.refresh)
        ok(f"{where} 폴더에 저장했습니다 ({time.time() - t0:.0f}초)")
        print(f"     기간 {m['start']} ~ {m['end']} · 매달 상위 {m['top_n']}종목 · 전체 {m['codes']}종목(상장폐지 {m['delisted']})")
        print(f"     데이터 지문: {m['fingerprint']}")
        if folder:
            print(f"     이 데이터로 백테스트: uv run kit backtest <전략 파일> --data {args.data}")
    elif args.action == "pack":
        out, m = data.pack(cfg, end=args.end, folder=folder)
        ok(f"묶었습니다: {_rel(out)} ({out.stat().st_size / 1e6:.0f}MB)")
        print(f"     기간 {m['start']} ~ {m['end']} · 전체 {m['codes']}종목(상장폐지 {m['delisted']}) · 데이터 지문: {m['fingerprint']}")
    elif args.action == "unpack":
        if not args.file:
            raise KitError("zip 파일 경로를 적어 주세요. 예: uv run kit data unpack C:/Users/me/Downloads/data.zip")
        good, m = data.unpack(args.file, folder=folder)
        if good:
            ok(f"풀었습니다: {m['start']} ~ {m['end']} · 전체 {m['codes']}종목(상장폐지 {m['delisted']}) · 지문 {m['fingerprint']}")
        else:
            fail(m)
            return 1
    elif args.action == "verify":
        good, m = data.verify(folder)
        if good:
            ok(f"데이터가 받았을 때와 같습니다 · 지문 {m['fingerprint']}")
        else:
            fail(m)
            return 1
    elif args.action == "info":
        m = data.describe(folder)
        if m is None:
            warn(f"{where} 폴더에 데이터가 없습니다.")
            return 1
        print(json.dumps({k: v for k, v in m.items() if k != "files"}, ensure_ascii=False, indent=2))
    elif args.action == "calendar":
        panel = data.load_panel(cfg, folder)
        days = panel.dates
        if args.start:
            days = days[days >= pd.Timestamp(args.start)]
        if args.end:
            days = days[days <= pd.Timestamp(args.end)]
        out = OUTPUTS / f"calendar_{days[0]:%Y-%m-%d}_{days[-1]:%Y-%m-%d}.csv"
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": days.strftime("%Y-%m-%d")}).to_csv(out, index=False, lineterminator=chr(10))
        ok(f"거래일 {len(days)}일: {days[0].date()} ~ {days[-1].date()} -> {_rel(out)}")
    elif args.action == "minute":
        if not args.file:
            raise KitError("종목코드를 적어 주세요. 예: uv run kit data minute 005930")
        code = str(args.file).zfill(6)
        market = None
        stocks_path = (folder or data.DATA) / "stocks.csv"
        if stocks_path.exists():
            st = pd.read_csv(stocks_path, dtype={"code": str}, encoding="utf-8-sig")
            market = dict(zip(st["code"], st["market"])).get(code)
        path, rows = data.save_minute(code, interval=args.interval, days=args.days, market=market)
        ok(f"{_rel(path)} 에 쌓았습니다 (지금 {rows:,}줄)")
    return 0


# ---------------------------------------------------------------- backtest

def _period(args, cfg, default_start, default_end):
    return (pd.Timestamp(args.start) if args.start else default_start,
            pd.Timestamp(args.end) if args.end else default_end)


def _research_period(args, cfg):
    """연구 명령의 기간. 연구 기간 끝을 넘기면 멈추고 알려 준다 (research_lock)."""
    start, end = _period(args, cfg, cfg.data_start, cfg.research_end)
    if cfg.research_lock and end > cfg.research_end:
        raise KitError(f"연구는 {cfg.research_end.date()}까지의 데이터로만 합니다. "
                       f"모의투자 기간({cfg.compare_start.date()} ~ {cfg.compare_end.date()})은 마지막에 "
                       "'uv run kit submit'으로 한 번 계산합니다.")
    return start, end


def _guard_or_fail(path):
    """전략 파일 점검. 문제가 있으면 줄마다 알려 주고 False."""
    problems = guard.check_file(path)
    for line, msg in problems:
        fail(f"{Path(path).name} {line}줄: {msg}")
    return not problems


def cmd_backtest(args):
    cfg = load_config()
    start, end = _research_period(args, cfg)
    if not _guard_or_fail(args.file):
        print("     전략 파일을 고친 뒤 다시 실행해 주세요. (규칙: docs/strategy-guide.md)")
        return 1
    panel = data.load_panel(cfg, args.data)
    strategy = load_strategy(args.file)
    if args.cost_x != 1.0:  # 비용 민감도: 수수료 · 세금 · 슬리피지를 배수로
        import dataclasses
        tax = {m: [(d, r * args.cost_x) for d, r in rows] for m, rows in cfg.sell_tax.items()}
        cfg = dataclasses.replace(cfg, commission=cfg.commission * args.cost_x, slippage=cfg.slippage * args.cost_x,
                                  sell_tax=tax)
        warn(f"비용을 {args.cost_x}배로 계산합니다.")
    t0 = time.time()
    result = run_backtest(strategy, panel, cfg, start, end)
    out_dir = Path(args.out) if args.out else OUTPUTS / Path(args.file).stem
    save_result(result, out_dir, data.load_index(panel.dates, args.data), person=args.name or "",
                extra_meta=_data_meta(args.data))
    s = result.summary
    if args.quiet:
        print(json.dumps({"total_return": s["total_return"], "final_equity": s["final_equity"]}))
        return 0
    head(f"{strategy.name} ({rebalance_label(strategy.rebalance)} 리밸런싱)")
    print(f"     기간       {s['start']} ~ {s['end']} ({s['days']}거래일, {time.time() - t0:.1f}초)")
    print(f"     최종 자산  {won(s['final_equity'])} (시작 {won(s['initial_cash'])})")
    print(f"     총수익률   {pct(s['total_return'])} · 연평균 {pct(s['cagr'])}")
    print(f"     최대 낙폭  {pct(s['mdd'])} · 샤프 지수 {s['sharpe']}")
    print(f"     거래       {s['trades']}건 · 수수료 {won(s['fees'])} · 세금 {won(s['taxes'])}")
    for note in result.notes[:5]:
        warn(note)
    print(f"\n결과 파일 (규격: docs/result-spec.md): {_rel(out_dir)}")
    print("     result.csv 날짜별 평가금액 · weights.csv 비중 · trades.csv 거래 · meta.json 정보 · report.html 리포트")
    return 0


def _data_meta(folder=None):
    m = data.describe(folder) or {}
    return {"data_fingerprint": m.get("fingerprint"), "data_start": m.get("start"), "data_end": m.get("end"),
            "kit_version": __version__}


def cmd_lookahead(args):
    cfg = load_config()
    start, end = _research_period(args, cfg)
    panel = data.load_panel(cfg, args.data)
    good, msg = lookahead.check(args.file, panel, cfg, start, end)
    (ok if good else fail)(msg)
    return 0 if good else 1


# ---------------------------------------------------------------- new · submit

def _safe_name(text):
    text = re.sub(r"[^\w가-힣-]+", "_", str(text).strip())
    return text.strip("_") or "strategy"


def cmd_new(args):
    name = _safe_name(args.name)
    path = STRATEGIES / f"{name}.py"
    if path.exists():
        raise KitError(f"이미 있는 파일입니다: {_rel(path)}")
    shutil.copyfile(TEMPLATES / "strategy_template.py", path)
    ok(f"새 전략 파일을 만들었습니다: {_rel(path)}")
    return 0


def cmd_submit(args):
    from .data import now_kst
    from . import result as spec

    cfg = load_config()
    path = Path(args.file)
    start = pd.Timestamp(args.start) if args.start else cfg.compare_start
    end = pd.Timestamp(args.end) if args.end else cfg.compare_end
    head("1. 코드 점검")
    if not _guard_or_fail(path):
        return 1
    ok("파일 · 인터넷 접근 없음 · 종목코드 · 이름 · 날짜를 직접 적지 않음")
    panel = data.load_panel(cfg, full=True)
    if panel.dates[0] > start or panel.dates[-1] < end - pd.Timedelta(days=5):
        raise KitError(f"데이터가 {panel.dates[0].date()} ~ {panel.dates[-1].date()}입니다. 기간 {start.date()} ~ {end.date()}이 "
                       "들어 있는 데이터가 필요합니다. 'uv run kit data download'로 데이터를 다시 받아 주세요.")
    head("2. 미래 데이터 · 무작위 검사")
    good, msg = lookahead.check(path, panel, cfg, cfg.data_start, min(end, panel.dates[-1]))
    (ok if good else fail)(msg)
    if not good:
        return 1
    head(f"3. 결과 ({start.date()} ~ {end.date()})")
    result = run_backtest(load_strategy(path), panel, cfg, start, end)
    s = result.summary
    print(f"     최종 평가금액 {won(s['final_equity'])} · 총수익률 {pct(s['total_return'])} · 최대 낙폭 {pct(s['mdd'])} · 거래 {s['trades']}건")
    csv_bytes = spec.files_for(result, args.name, team=args.team or "")["result.csv"]
    errors, _ = spec.validate(pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig"), calendar=panel.dates,
                              start=start, end=end, initial_cash=cfg.initial_cash)
    if errors:
        raise KitError("결과 CSV가 양식에 맞지 않습니다: " + errors[0])
    SUBMISSIONS.mkdir(parents=True, exist_ok=True)
    prefix = f"{_safe_name(args.team)}_" if args.team else ""
    out = SUBMISSIONS / f"{prefix}{_safe_name(args.name)}_{_safe_name(path.stem)}.csv"
    out.write_bytes(csv_bytes)
    print()
    ok(f"결과 CSV를 만들었습니다: {_rel(out)}")
    print("     이 CSV 파일 하나를 진행자에게 보내 주세요. 파일 안의 숫자는 고치지 않습니다.")
    return 0


def cmd_validate(args):
    from . import result as spec

    cfg = load_config()
    try:
        calendar = data.load_panel(cfg, full=True).dates
    except KitError:
        calendar = None
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    bad = 0
    for p in [Path(x) for x in args.files]:
        try:
            sub = spec.read_submission(p)
        except Exception as e:
            fail(f"{p.name}: {e}")
            bad += 1
            continue
        errors, warns = spec.validate(sub["result"], None, calendar, start, end, cfg.initial_cash)
        r = sub["result"]
        head(f"{p.name} · {sub['name']} · {sub['strategy']}")
        if {"date", "equity"} <= set(r.columns) and len(r):
            last = pd.to_numeric(r["equity"], errors="coerce").iloc[-1]
            print(f"     기간 {r['date'].iloc[0]} ~ {r['date'].iloc[-1]} ({len(r)}일) · 최종 평가금액 {won(float(last))}")
        for w in warns:
            warn(w)
        for e in errors:
            fail(e)
        if not errors:
            ok("결과 CSV 양식에 맞습니다.")
        bad += bool(errors)
    return 1 if bad else 0


# ---------------------------------------------------------------- race

def cmd_race(args):
    import webbrowser

    from .race import run_race

    cfg = load_config()
    try:
        panel = data.load_panel(cfg, full=True)
        calendar, index_table = panel.dates, data.load_index(panel.dates)
    except KitError:
        calendar, index_table = None, None
        warn("데이터가 없어 코스피 · 코스닥 비교선 없이 만듭니다.")
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    folder = Path(args.folder) if args.folder else SUBMISSIONS
    html, rows = run_race(folder, cfg, calendar, index_table, start, end)
    head("순위 (마지막 날 평가금액)")
    for r in rows:
        team = f" [{r['팀']}]" if r.get("팀") else ""
        print(f"     {r['순위']:>2}. {r['이름']}{team} · {r['전략']} : {won(r['최종 평가금액'])} ({pct(r['총수익률'])})")
    print(f"\n레이스 화면: {_rel(html)}  ([재생]을 눌러 주세요)")
    if not args.no_open:
        webbrowser.open(Path(html).resolve().as_uri())
    return 0


# ---------------------------------------------------------------- keys (외부 연동 키)

def cmd_keys(args):
    import getpass
    import importlib

    from .connectors import GROUPS
    from .connectors.base import ENV_FILE, KEYS, get_key, mask, write_key

    if args.action == "set":
        if not args.name or args.name not in KEYS:
            raise KitError("키 이름을 적어 주세요. 예: uv run kit keys set DART_API_KEY (이름 목록: uv run kit keys)")
        value = getpass.getpass(f"{args.name} 값을 붙여 넣고 Enter (화면에 보이지 않습니다): ").strip()
        if not value:
            raise KitError("값이 비어 있습니다.")
        write_key(args.name, value)
        ok(f"{args.name}을(를) {_rel(ENV_FILE)}에 저장했습니다 ({mask(value)}). 이 파일은 저장소에 올라가지 않습니다.")
        return 0
    if args.action == "test":
        bad = 0
        head("외부 연동 점검")
        for group, (module, names) in GROUPS.items():
            if args.name and args.name != group:
                continue
            if names and not all(get_key(n, required=False) for n in names):
                if group == "news" and get_key("NAVER_CLIENT_ID", required=False):
                    pass
                elif group == "ecos":
                    pass  # 키가 없으면 시험용 키로 확인
                else:
                    print(f"     {group:<6} 키 없음 (건너뜀)")
                    continue
            t0 = time.time()
            try:
                msg = importlib.import_module(module).ping()
                ok(f"{group:<6} {msg} ({time.time() - t0:.1f}초)")
            except Exception as e:
                bad += 1
                fail(f"{group:<6} {str(e).splitlines()[0][:150]}")
        return 1 if bad else 0
    head("외부 연동 키 (값은 끝 3자리만 표시)")
    for name, (desc, where, group) in KEYS.items():
        value = get_key(name, required=False)
        state = mask(value) if value else "없음"
        print(f"     {name:<24} {state:<12} {desc}")
    print(f"\n저장 위치: {_rel(ENV_FILE)} (저장소에 올라가지 않음)")
    print("설정: uv run kit keys set <키 이름>  (키 값은 터미널에서 직접 입력)")
    print("확인: uv run kit keys test        자세한 설명: docs/connectors.md")
    return 0


# ---------------------------------------------------------------- screen (오늘의 종목 리스트)

def cmd_screen(args):
    from .market import Market
    from .engine import normalize_weights
    from .helpers import KEEP

    cfg = load_config()
    panel = data.load_panel(cfg, args.data)
    day = pd.Timestamp(args.date) if args.date else panel.dates[-1]
    i = int(panel.dates.searchsorted(day, side="right")) - 1
    if i < 0:
        raise KitError("데이터 기간 안의 날짜를 적어 주세요.")
    strategy = load_strategy(args.file)
    raw = strategy.decide(Market(panel, i))
    head(f"{strategy.name} · {panel.dates[i].date()} 장 마감 기준 고른 종목")
    if raw is KEEP:
        print("     KEEP: 이날은 들고 있는 그대로 둡니다.")
        return 0
    notes = []
    picks = normalize_weights(raw, {c: k for k, c in enumerate(panel.codes)}, panel.member.iloc[i].to_numpy(), notes)
    if not picks:
        print("     고른 종목 없음 (전부 현금)")
    price = panel.price.iloc[i]
    rows = []
    for code, w in sorted(picks.items(), key=lambda x: -x[1]):
        rows.append({"code": code, "name": panel.name_on(code, panel.dates[i]), "weight": round(w, 4),
                     "price": price.get(code)})
        print(f"     {code}  {panel.name_on(code, panel.dates[i]):<14} 비중 {w:6.1%}  종가 {price.get(code, float('nan')):>12,.0f}원")
    for n in sorted(set(notes))[:5]:
        warn(n)
    if rows:
        out = OUTPUTS / f"screen_{Path(args.file).stem}_{panel.dates[i]:%Y%m%d}.csv"
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"\n저장: {_rel(out)}")
    return 0


# ---------------------------------------------------------------- factor · event (연구 도구)

def cmd_factor(args):
    from .lab import robustness, signals

    if args.name == "list":
        head("기본 신호")
        for k, (_, desc) in signals.SIGNALS.items():
            print(f"     {k:<16} {desc}")
        return 0
    cfg = load_config()
    panel = data.load_panel(cfg, args.data)
    sig = signals.compute(panel, args.name)
    res = robustness.report(sig, panel, horizon=args.horizon, start=args.start, end=args.end, placebo_n=args.placebo)
    s, r = res["summary"], res["robust"]
    head(f"신호 검증: {args.name} ({s['start']} ~ {s['end']}, {s['days']}일, 보유 {s['horizon']}거래일)")
    print(f"     IC 평균 {s['ic_mean']:+.4f} (t {s['ic_t']}) · IC가 플러스인 날 {s['ic_positive_share']:.0%}")
    print(f"     95% 신뢰구간 {r['ic_ci_95']} · 앞 절반 {r['halves']['first_half']:+.4f} · 뒤 절반 {r['halves']['second_half']:+.4f}")
    print(f"     해마다 부호가 같은 해 {s['years_same_sign']}/{s['years']}")
    q = s["quantile_mean"]
    print("     5분위 평균 수익률: " + " · ".join(f"{k}분위 {v:+.2%}" for k, v in q.items()))
    print(f"     맨 위 - 맨 아래 {s['spread_mean']:+.2%} (t {s['spread_t']}) · 비용 빼기 전")
    if r["placebo"]:
        p = r["placebo"]
        print(f"     플라시보(무작위로 섞기 {p['n']}번): 섞은 IC 95% {p['ic_placebo_95']} · p값 {p['p_value']}")
    out = OUTPUTS / f"factor_{args.name}"
    out.mkdir(parents=True, exist_ok=True)
    res["ic"].rename("ic").to_csv(out / "ic.csv", encoding="utf-8-sig", lineterminator="\n")
    res["quantiles"].to_csv(out / "quantiles.csv", encoding="utf-8-sig", lineterminator="\n")
    res["yearly"].to_csv(out / "yearly.csv", encoding="utf-8-sig", lineterminator="\n")
    (out / "summary.json").write_text(json.dumps({"summary": s, "robust": r}, ensure_ascii=False, indent=2, default=str),
                                      encoding="utf-8")
    print(f"\n결과 파일: {_rel(out)}")
    return 0


def cmd_event(args):
    from .lab import event_study

    cfg = load_config()
    panel = data.load_panel(cfg, args.data)
    events = pd.read_csv(args.file, dtype={"code": str}, encoding="utf-8-sig")
    res = event_study.run(events, panel, horizon=args.horizon)
    s = res["summary"]
    head(f"이벤트 스터디 ({s['events']}건, {s['horizon']}거래일)")
    for row in res["curve"].itertuples(index=False):
        if row.day in (1, 2, 3, 5, 10, 20, s["horizon"]):
            print(f"     {row.day:>3}일째 누적 초과수익 {row.car_mean:+.2%} (t {row.t}) · 플러스 비율 {row.positive_share:.0%}")
    out = OUTPUTS / f"event_{Path(args.file).stem}"
    out.mkdir(parents=True, exist_ok=True)
    res["curve"].to_csv(out / "curve.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    res["events"].to_csv(out / "events.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"\n결과 파일: {_rel(out)} (비용 빼기 전)")
    return 0


# ---------------------------------------------------------------- main

def build_parser():
    p = argparse.ArgumentParser(prog="kit", description="AI와 함께 하는 국내 주식 연구 키트")
    sub = p.add_subparsers(dest="command", metavar="<명령>")

    c = sub.add_parser("check", help="설치 점검 (샘플 전략이 모두 같은 숫자를 내는지)")
    c.add_argument("--update-expected", action="store_true", help=argparse.SUPPRESS)
    c.set_defaults(func=cmd_check)

    sub.add_parser("sources", help="데이터 출처 연결 점검").set_defaults(func=cmd_sources)

    d = sub.add_parser("data", help="데이터 받기 · 풀기 · 확인 · 분봉 쌓기")
    d.add_argument("action", choices=["download", "pack", "unpack", "verify", "info", "calendar", "minute"],
                   help="download 받기 · unpack zip 풀기 · verify 확인 · info 현황 · calendar 거래일 목록 · minute 분봉 쌓기 · pack 묶기(진행자)")
    d.add_argument("file", nargs="?", help="unpack: zip 경로 · minute: 종목코드")
    d.add_argument("--start", help="시작일 (download 기본: 2000-01-01, 가장 이른 날: 1995-05-02)")
    d.add_argument("--end", help="끝 날짜 (download · pack 기본: 설정의 데이터 끝 · 최신까지는 today)")
    d.add_argument("--top", type=int, help="매달 시가총액 상위 몇 종목을 투자 대상으로 할지 (기본 200)")
    d.add_argument("--data", help="데이터 폴더 (기본: data). 개인 연구용 데이터는 research/ 아래 다른 폴더에")
    d.add_argument("--refresh", action="store_true", help="원천 파일을 새로 받기")
    d.add_argument("--interval", default="1m", help="분봉 간격 (1m · 5m · 60m 등)")
    d.add_argument("--days", type=int, default=8, help="분봉: 최근 며칠")
    d.set_defaults(func=cmd_data)

    n = sub.add_parser("new", help="새 전략 파일 만들기")
    n.add_argument("name", help="전략 이름 (파일 이름이 됨)")
    n.set_defaults(func=cmd_new)

    for name, fn, text in (("backtest", cmd_backtest, "전략 백테스트 (결과는 규격 CSV로 저장)"), ("lookahead", cmd_lookahead, "미래 데이터 사용 검사")):
        b = sub.add_parser(name, help=text)
        b.add_argument("file", help="전략 파일 경로 (예: strategies/my_strategy.py)")
        b.add_argument("--start", help="시작일 (기본: 연구 기간 시작)")
        b.add_argument("--end", help="끝 날짜 (기본: 연구 기간 끝)")
        b.add_argument("--data", help="데이터 폴더 (기본: data)")
        if name == "backtest":
            b.add_argument("--out", help="결과 폴더 (기본: outputs/<파일 이름>)")
            b.add_argument("--name", help="결과 CSV의 name 칸에 넣을 이름")
            b.add_argument("--cost-x", type=float, default=1.0, help="비용 배수 (예: 1.5 = 수수료 · 세금 1.5배)")
            b.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
        b.set_defaults(func=fn)

    s = sub.add_parser("submit", help="모의투자 기간 결과 CSV 만들기 (진행자에게 보낼 파일)")
    s.add_argument("file", help="전략 파일 경로")
    s.add_argument("--name", required=True, help="이름 또는 닉네임")
    s.add_argument("--team", help="팀 이름 (레이스에서 팀별 평균을 낼 때 씀)")
    s.add_argument("--start", help="기간 시작 (기본: 설정의 모의투자 기간)")
    s.add_argument("--end", help="기간 끝")
    s.set_defaults(func=cmd_submit)

    v = sub.add_parser("validate", help="결과 CSV가 양식에 맞는지 점검")
    v.add_argument("files", nargs="+", help="결과 CSV 경로 (여러 개 가능)")
    v.add_argument("--start", help="정한 기간 시작 (있으면 기간도 확인)")
    v.add_argument("--end", help="정한 기간 끝")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("race", help="진행자용: 모은 결과 CSV로 수익 레이스 화면 만들기 (브라우저로 열림)")
    r.add_argument("folder", nargs="?", help="결과 CSV를 모은 폴더 (기본: submissions)")
    r.add_argument("--start", help="시작일 (기본: CSV들의 공통 기간)")
    r.add_argument("--end", help="끝 날짜 (기본: CSV들의 공통 기간)")
    r.add_argument("--no-open", action="store_true", help="브라우저로 열지 않기")
    r.set_defaults(func=cmd_race)

    k = sub.add_parser("keys", help="외부 연동 키 보기 · 설정 · 점검 (DART · 뉴스 · ECOS · 증권사 등)")
    k.add_argument("action", nargs="?", default="list", choices=["list", "set", "test"], help="list 보기 · set 설정 · test 점검")
    k.add_argument("name", nargs="?", help="set: 키 이름 · test: 그룹 (dart · news · ecos · kis · krx · world)")
    k.set_defaults(func=cmd_keys)

    sc = sub.add_parser("screen", help="전략이 그날 고르는 종목 리스트 보기")
    sc.add_argument("file", help="전략 파일 경로")
    sc.add_argument("--date", help="기준일 (기본: 데이터 마지막 날)")
    sc.add_argument("--data", help="데이터 폴더 (기본: data)")
    sc.set_defaults(func=cmd_screen)

    f = sub.add_parser("factor", help="신호 검증 (IC · 5분위 · 우연 검사). 'kit factor list'로 신호 목록")
    f.add_argument("name", help="신호 이름 또는 list")
    f.add_argument("--horizon", type=int, default=5, help="보유 거래일 (기본 5)")
    f.add_argument("--start", help="시작일")
    f.add_argument("--end", help="끝 날짜")
    f.add_argument("--placebo", type=int, default=30, help="무작위 섞기 횟수 (0이면 건너뜀)")
    f.add_argument("--data", help="데이터 폴더 (기본: data)")
    f.set_defaults(func=cmd_factor)

    ev = sub.add_parser("event", help="이벤트 스터디 (date · code 열이 있는 CSV)")
    ev.add_argument("file", help="이벤트 CSV 경로")
    ev.add_argument("--horizon", type=int, default=10, help="볼 거래일 수 (기본 10)")
    ev.add_argument("--data", help="데이터 폴더 (기본: data)")
    ev.set_defaults(func=cmd_event)
    return p


def main(argv=None):
    setup()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args) or 0
    except KitError as e:
        fail(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
