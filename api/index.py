import os
import sys

# Vercel serverless：把项目根目录加入 sys.path，再导出 FastAPI ASGI app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
