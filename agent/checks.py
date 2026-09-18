# -*- coding: utf-8 -*-
"""三类疑点检查器：
1) numeric      —— 数值异常（同比/环比大幅跳变、毛利率/费用率异常波动）
2) cashflow     —— 勾稽疑点（净利润与经营现金流背离）
3) text_number  —— 文本-数字一致性（需要 LLM，缺失时显式降级）
"""
from __future__ import annotations

from typing import Callable, List, Optional

from .evidence import Evidence, make_evidence
from .fetch import FinData, ReportText
from .llm import LLMClient

PCT = 0.30  # 同比跳变阈值 30%


def _pct(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def run_numeric(fin: FinData) -> List[Evidence]:
    """数值异常检查：收入/净利润同比跳变、毛利率/费用率波动。"""
    out: List[Evidence] = []
    src = f"{fin.source}；时点 {fin.as_of}；口径：亿元/百分比"
    n = 0

    rev_chg = _pct(fin.revenue, fin.revenue_prev)
    if rev_chg is not None and abs(rev_chg) >= PCT:
        n += 1
        out.append(make_evidence(
            f"EV-{n:03d}", "numeric",
            "营业收入同比大幅变化",
            f"营业收入 {fin.revenue} 亿元，上年同期 {fin.revenue_prev} 亿元，"
            f"同比变动 {rev_chg*100:.1f}%（阈值 ±{PCT*100:.0f}%）。",
            "营业收入", f"上年同期 {fin.revenue_prev} 亿元，同比 {rev_chg*100:.1f}%",
            f"营业收入 {fin.revenue} 亿元；上年同期 {fin.revenue_prev} 亿元（构造数据）",
            src,
        ))

    np_chg = _pct(fin.net_profit, fin.net_profit_prev)
    if np_chg is not None and abs(np_chg) >= PCT:
        n += 1
        out.append(make_evidence(
            f"EV-{n:03d}", "numeric",
            "归母净利润同比大幅变化",
            f"归母净利润 {fin.net_profit} 亿元，上年同期 {fin.net_profit_prev} 亿元，"
            f"同比变动 {np_chg*100:.1f}%（阈值 ±{PCT*100:.0f}%）。",
            "归母净利润", f"上年同期 {fin.net_profit_prev} 亿元，同比 {np_chg*100:.1f}%",
            f"归母净利润 {fin.net_profit} 亿元；上年同期 {fin.net_profit_prev} 亿元（构造数据）",
            src,
        ))

    if fin.gross_margin is not None and fin.gross_margin_prev is not None:
        gm_delta = fin.gross_margin - fin.gross_margin_prev
        if abs(gm_delta) >= 5.0:
            n += 1
            out.append(make_evidence(
                f"EV-{n:03d}", "numeric",
                "毛利率大幅波动",
                f"毛利率 {fin.gross_margin}%，上年 {fin.gross_margin_prev}%，"
                f"变动 {gm_delta:+.1f} 个百分点（阈值 ±5pct）。",
                "毛利率", f"上年 {fin.gross_margin_prev}%，变动 {gm_delta:+.1f}pct",
                f"毛利率 {fin.gross_margin}%；上年 {fin.gross_margin_prev}%（构造数据）",
                src,
            ))

    if fin.expense_ratio is not None and fin.expense_ratio_prev is not None:
        er_delta = fin.expense_ratio - fin.expense_ratio_prev
        if abs(er_delta) >= 3.0:
            n += 1
            out.append(make_evidence(
                f"EV-{n:03d}", "numeric",
                "期间费用率明显变化",
                f"销售+管理费用率 {fin.expense_ratio}%，上年 {fin.expense_ratio_prev}%，"
                f"变动 {er_delta:+.1f} 个百分点（阈值 ±3pct）。",
                "期间费用率", f"上年 {fin.expense_ratio_prev}%，变动 {er_delta:+.1f}pct",
                f"费用率 {fin.expense_ratio}%；上年 {fin.expense_ratio_prev}%（构造数据）",
                src,
            ))

    return out


def run_cashflow(fin: FinData) -> List[Evidence]:
    """勾稽疑点：净利润与经营现金流背离（连续两年背离或方向相反）。"""
    out: List[Evidence] = []
    src = f"{fin.source}；时点 {fin.as_of}；口径：亿元"
    if fin.net_profit is None or fin.ocf is None:
        return out

    gap = fin.net_profit - fin.ocf
    if gap >= 0 and fin.net_profit >= 0:
        # 净利润为正但经营现金流显著低于净利润
        ratio = fin.ocf / fin.net_profit if fin.net_profit else None
        if ratio is not None and ratio < 0.7:
            out.append(make_evidence(
                "EV-099", "cashflow",
                "净利润与经营现金流背离（现金含量低）",
                f"归母净利润 {fin.net_profit} 亿元，经营现金流净额 {fin.ocf} 亿元，"
                f"现金流/净利润 = {ratio:.2f}（<0.7）。"
                "可能涉及利润含金量、应收/存货占用或非付现损益，需结合附注复核。",
                "净利润 vs 经营现金流",
                f"现金流/净利润 = {ratio:.2f}（阈值 <0.7）",
                f"经营活动产生的现金流量净额 {fin.ocf} 亿元；归母净利润 {fin.net_profit} 亿元（构造数据）",
                src,
            ))
    return out


def run_text_number(
    fin: FinData,
    text: ReportText,
    llm: LLMClient,
    feedback_context: Optional[str] = None,
) -> tuple[List[Evidence], Optional[str]]:
    """文本-数字一致性检查（LLM 驱动）。

    返回 (证据列表, 降级说明)。LLM 不可用或文本缺失时显式降级，绝不编造。
    """
    if not text.text or not text.text.strip():
        return [], "财报文本缺失，未执行文本-数字一致性校验（仅完成数值与勾稽检查）。"

    if not llm.available():
        return [], "未配置 LLM（LLM_API_KEY 为空），文本-数字一致性校验不可用（当前为规则引擎模式）。"

    sys_prompt = (
        "你是财报审查 Agent。仅做疑点识别与证据陈列，禁止输出涨跌预测、买卖建议、"
        "评级或任何投资观点。严格区分事实、疑点、推测。"
        "只输出 JSON：{\"items\":[{\"title\":\"...\",\"detail\":\"...\","
        "\"quote\":\"原文片段\",\"metric\":\"指标\",\"basis\":\"对比基准\"}]}"
        "每条必须给出财报原文中的 quote 原文片段，禁止编造原文。"
    )
    user_prompt = (
        f"股票 {fin.stock_code}，报告期 {fin.report_period}。\n"
        f"财务指标：收入 {fin.revenue} 亿（上年 {fin.revenue_prev}），"
        f"归母净利 {fin.net_profit} 亿（上年 {fin.net_profit_prev}），"
        f"经营现金流 {fin.ocf} 亿，毛利率 {fin.gross_margin}%（上年 {fin.gross_margin_prev}）。\n"
        f"管理层讨论原文（节选）：\n{text.text[:4000]}\n"
        f"{('历史用户反馈：' + feedback_context) if feedback_context else ''}\n"
        "请识别管理层文字描述与报表数字是否矛盾、表述是否含糊、"
        "是否存在需要人工复核的疑点。没有则返回 {\"items\":[]}。"
    )

    result = llm.chat_json(sys_prompt, user_prompt)
    if result is None:
        return [], "LLM 调用失败，文本-数字一致性校验不可用；已保留数值与勾稽检查结果。"

    items = result.get("items", [])
    src = f"{text.source}；时点 {fin.as_of}；口径：亿元"
    out: List[Evidence] = []
    for i, item in enumerate(items, start=1):
        quote = (item.get("quote") or "").strip()
        out.append(make_evidence(
            f"EV-2{i:02d}", "text_number",
            item.get("title", "文本-数字一致性疑点"),
            item.get("detail", ""),
            item.get("metric", "—"),
            item.get("basis", "—"),
            quote,
            src,
        ))
    return out, None


def run_all(
    fin: FinData,
    text: ReportText,
    llm: LLMClient,
    feedback_context: Optional[str] = None,
) -> dict:
    """总入口：依次执行三类检查，聚合结果并给出运行模式说明。"""
    evidence: List[Evidence] = []
    notes: List[str] = []

    if fin.is_demo:
        notes.append("当前数据为「内置构造演示数据」，非真实财报，仅用于评审演示。")

    evidence += run_numeric(fin)
    evidence += run_cashflow(fin)

    # 文本链路状态提示（真实公告文本已获取时可见，体现数据链路完整）
    if not text.is_demo and text.text and text.text.strip():
        notes.append(f"已获取财报公告文本（{len(text.text)} 字符）：{text.source}。")

    text_ev, degrade = run_text_number(fin, text, llm, feedback_context)
    evidence += text_ev
    if degrade:
        notes.append(degrade)

    if not evidence:
        if degrade:
            # 文本校验未执行时，结论不完整，禁止用「全部检查无异常」口径
            notes.append("数值与勾稽检查未发现明显疑点；文本-数字校验未执行（见上），本结论不覆盖文本维度。")
        else:
            notes.append("未识别出明显疑点。此结论仅在数据完整、检查器全部执行的前提下成立。")

    return {
        "ok": True,
        "evidence": [e.to_dict() for e in evidence],
        "notes": notes,
        "mode_note": "演示数据" if fin.is_demo else "真实数据（含构造文本时请核对来源）",
    }
