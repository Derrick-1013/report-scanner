# -*- coding: utf-8 -*-
"""证据与置信标签模型：所有疑点必须绑定证据、来源、时点、口径与标签。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# 置信标签（强制三选一，禁止缺失）
LABEL_FACT = "事实确认"          # 数据与原文直接匹配，客观披露
LABEL_REVIEW = "需要人工复核"     # 存在异常信号，但需结合业务二次确认
LABEL_SPEC = "仅推测"             # AI 推断，无直接原文支撑


@dataclass
class Evidence:
    """单条疑点证据。"""

    id: str
    check_type: str                # numeric / cashflow / text_number
    title: str
    detail: str
    metric: str                    # 涉及指标
    baseline: str                  # 对比基准（同比/环比/占比等）
    quote: str                     # 原文片段（可为空，空则必须打仅推测）
    source: str                    # 来源 + 时点 + 口径
    label: str                     # 三选一标签
    feedback: Optional[str] = None # confirmed / false_positive / None

    def to_dict(self) -> dict:
        return asdict(self)


def make_evidence(
    ev_id: str,
    check_type: str,
    title: str,
    detail: str,
    metric: str,
    baseline: str,
    quote: str,
    source: str,
) -> Evidence:
    """按证据强度自动决定标签：无原文引用 -> 仅推测；有引用 -> 需人工复核。"""
    if not quote or not quote.strip():
        label = LABEL_SPEC
    else:
        label = LABEL_REVIEW
    return Evidence(
        id=ev_id,
        check_type=check_type,
        title=title,
        detail=detail,
        metric=metric,
        baseline=baseline,
        quote=quote,
        source=source,
        label=label,
    )


def no_evidence_result(message: str) -> dict:
    """数据缺失/失败时的结构化响应：绝不静默生成'正常'结论。"""
    return {
        "ok": False,
        "message": message,
        "evidence": [],
        "mode_note": None,
    }
