import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from tests.db_guard import install_global_safety_guard
except ImportError:
    from .db_guard import install_global_safety_guard

install_global_safety_guard()
