"""화면 출력 도우미. 윈도우 콘솔(cp949)에서도 깨지지 않는 글자만 쓴다."""

import sys


class KitError(Exception):
    """사용자에게 그대로 보여 줄 오류."""


def setup():
    """터미널 화면이면 그대로 두고, 다른 프로그램(AI 확장 등)이 출력을 받아 가면 UTF-8로 내보낸다.

    윈도우는 출력을 파이프로 넘길 때 기본 인코딩(cp949 등)을 써서, UTF-8로 읽는 도구에서 한글이 깨진다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ok(msg):
    print(f"[OK] {msg}")


def warn(msg):
    print(f"[주의] {msg}")


def fail(msg):
    print(f"[실패] {msg}")


def head(msg):
    print()
    print(f"== {msg} ==")


def won(x):
    return f"{x:,.0f}원"


def pct(x):
    if x is None or x != x:
        return "-"
    return f"{x * 100:+.2f}%"
