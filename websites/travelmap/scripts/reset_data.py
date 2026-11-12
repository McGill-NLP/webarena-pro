from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.seed import reset_database


if __name__ == "__main__":
    reset_database()
    print("Environment reset to seeded demo state.")
