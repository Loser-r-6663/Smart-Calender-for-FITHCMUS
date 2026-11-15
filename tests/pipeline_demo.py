"""Run the crawler output through the real parser and task API pipeline. Uses the debug output from the Crawler"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Backend.Parser.test.pipeline_demo import main

if __name__ == "__main__":
    raise SystemExit(main())
