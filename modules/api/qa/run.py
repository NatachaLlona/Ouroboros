"""Run this module's independently owned QA suite."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from qa.run import main

if __name__ == "__main__":
    raise SystemExit(main(["--suite", "api", *sys.argv[1:]]))
