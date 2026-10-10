import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.argv = [sys.argv[0]] + (["--user", sys.argv[1]] if len(sys.argv) > 1 else []) + ["fetch"]

from cli import main

main()
