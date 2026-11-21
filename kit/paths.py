"""키트 안의 주요 폴더 위치."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent

CONFIG = ROOT / "config"
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
SUBMISSIONS = ROOT / "submissions"
STRATEGIES = ROOT / "strategies"
CACHE = ROOT / ".cache"

SAMPLE = PACKAGE / "sample"
TEMPLATES = PACKAGE / "templates"
REFERENCE = PACKAGE / "reference"

MINUTE = DATA / "minute"
