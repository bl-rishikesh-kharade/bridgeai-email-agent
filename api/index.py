import sys
from pathlib import Path

# Ensure root project directory is in python path for module imports
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from app.main import app  # noqa: E402
