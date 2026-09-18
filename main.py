# -*- coding: utf-8 -*-
"""财报疑点放大镜 —— Web 入口（FastAPI）。

运行：uvicorn main:app --host 0.0.0.0 --port 8000
或：  python main.py
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import checks, fetch
from agent.llm import LLMClient

load_dotenv()

app = FastAPI(title="财报疑点放大镜", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent / "frontend"

# 人机反馈存储（评审演示用内存实现；生产环境应落库）
_feedback_store: dict[str, str] = {}
_llm = LLMClient()

# 演示库中的可用标的，供前端下拉选择
DEMO_STOCKS = [
    {"code": "600519", "name": "贵州茅台（演示）"},
    {"code": "000001", "name": "平安银行（演示）"},
    {"code": "300750", "name": "宁德时代（演示）"},
]
DEMO_PERIODS = ["2025年报", "2024年报", "2023年报"]


class AnalyzeRequest(BaseModel):
    stock_code: str = Field(..., min_length=6, max_length=6, description="A股股票代码")
    report_period: str = Field(..., min_length=4, max_length=16, description="报告期，如 2024年报")


class FeedbackRequest(BaseModel):
    evidence_id: str
    action: str  # confirmed / false_positive


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm": _llm.available(),
        "data_mode": os.getenv("DATA_MODE", "auto"),
    }


@app.get("/api/stocks")
def stocks():
    return {"stocks": DEMO_STOCKS, "periods": DEMO_PERIODS}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """主链路：取数 -> 三类检查 -> 证据输出。失败时返回明确 message，不生成结论。"""
    try:
        fin = fetch.fetch_financial_data(req.stock_code, req.report_period)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到 {req.stock_code} {req.report_period} 的财务数据，无法执行审查。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        text = fetch.fetch_report_text(req.stock_code, req.report_period)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 组装配对用户历史反馈的上下文（人机闭环）
    feedback_context = None
    labels = {"confirmed": "用户确认", "false_positive": "用户误报"}
    if _feedback_store:
        feedback_context = "；".join(
            f"{eid}:{labels.get(act, act)}" for eid, act in _feedback_store.items()
        )

    result = checks.run_all(fin, text, _llm, feedback_context)
    return result


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if req.action not in ("confirmed", "false_positive"):
        raise HTTPException(status_code=400, detail="action 仅支持 confirmed / false_positive")
    _feedback_store[req.evidence_id] = req.action
    return {"ok": True, "evidence_id": req.evidence_id, "action": req.action}


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
