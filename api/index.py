import os
import sys

# Vercel serverless：把项目根目录加入 sys.path，再导出 FastAPI ASGI app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


@app.middleware("http")
async def path_debug(request: Request, call_next):
    if request.url.path == "/__debug":
        return JSONResponse({"path": request.url.path, "url": str(request.url)})
    return await call_next(request)
