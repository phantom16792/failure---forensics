# ✅ Correct
import sys
import os

api_dir = os.path.dirname(__file__)
backend_dir = os.path.abspath(os.path.join(api_dir, '..', 'backend'))

if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from app.main import app