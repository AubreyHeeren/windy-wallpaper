"""CI helper: writes version.py from the VERSION environment variable."""
import os
from pathlib import Path

version = os.environ.get("VERSION", "0.0.0")
Path(__file__).resolve().parent.parent.joinpath("version.py").write_text(
    f'__version__ = "{version}"\n', encoding="utf-8")
print("stamped version", version)
