# -*- coding: utf-8 -*-
"""数据获取层。

设计原则：
- DATA_MODE=demo  -> 使用内置构造数据，界面/结果中明确标注「演示数据」；
- DATA_MODE=auto  -> 优先真实接口（扶摇），任一环节失败则降级为演示数据并标注；
- DATA_MODE=real  -> 仅真实接口，失败直接抛错，绝不生成结论。

真实接口（扶摇，https://fuyao.aicubes.cn/docs/）：
- 利润表      GET /api/a-share/financials/income-statements
- 现金流量表  GET /api/a-share/financials/cash-flow-statements
- 财务指标    GET /api/a-share/financials/indicators
鉴权：请求头 X-api-key。统一信封 {code, message, request_id, data}，code=0 成功。
金额单位：原币元（CNY）；时间戳为毫秒（Asia/Shanghai）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

MODE_DEMO = "demo"
MODE_AUTO = "auto"
MODE_REAL = "real"

FUYAO_BASE = "https://fuyao.aicubes.cn"
CN_TZ = timezone(timedelta(hours=8))


@dataclass
class FinData:
    """财务指标快照（金额统一换算为亿元，百分比为百分点值）。"""

    is_demo: bool
    stock_code: str
    report_period: str
    as_of: str
    revenue: Optional[float]          # 营业收入（亿元）
    revenue_prev: Optional[float]     # 上年同期
    net_profit: Optional[float]       # 归母净利润（亿元）
    net_profit_prev: Optional[float]
    ocf: Optional[float]              # 经营现金流净额（亿元）
    gross_margin: Optional[float]     # 毛利率 %
    gross_margin_prev: Optional[float]
    expense_ratio: Optional[float]    # 销售+管理费用率 %
    expense_ratio_prev: Optional[float]
    source: str                       # 数据来源描述
    raw: dict                         # 原始响应


@dataclass
class ReportText:
    is_demo: bool
    stock_code: str
    report_period: str
    text: str
    source: str


# ============ 辅助：代码/报告期解析 ============

def _thscode_of(stock_code: str) -> str:
    """6 位 A 股代码 -> 带交易所后缀的 thscode。"""
    code = stock_code.strip()
    if not code.isdigit() or len(code) != 6:
        raise KeyError(f"股票代码需为 6 位数字：{stock_code}")
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{code}.SH"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _year_of(report_period: str) -> int:
    """'2024年报' -> 2024；取前 4 位数字。"""
    digits = "".join(ch for ch in report_period if ch.isdigit())
    if len(digits) < 4:
        raise KeyError(f"报告期格式非法：{report_period}（示例：2024年报）")
    return int(digits[:4])


def _pick_fy(items: list, year: int, field: Optional[str] = None):
    """从报表序列中取指定财年 FY 项（或其字段值）。"""
    for it in items:
        if it.get("fiscal_year") == year and it.get("fiscal_period") == "FY":
            return it.get(field) if field else it
    return None


# ============ 构造演示数据（仅用于评审演示，明确标注） ============

_DEMO_FIN = {
    "600519": {
        "2024年报": dict(revenue=1505.6, revenue_prev=1476.9, net_profit=862.3,
                         net_profit_prev=747.3, ocf=745.2, gross_margin=91.9,
                         gross_margin_prev=91.5, expense_ratio=10.2, expense_ratio_prev=10.8),
        "2023年报": dict(revenue=1476.9, revenue_prev=1275.5, net_profit=747.3,
                         net_profit_prev=627.2, ocf=665.9, gross_margin=91.5,
                         gross_margin_prev=91.6, expense_ratio=10.8, expense_ratio_prev=11.2),
    },
    "000001": {
        "2024年报": dict(revenue=3120.0, revenue_prev=3011.0, net_profit=451.0,
                         net_profit_prev=464.0, ocf=120.5, gross_margin=None,
                         gross_margin_prev=None, expense_ratio=None, expense_ratio_prev=None),
        "2023年报": dict(revenue=3011.0, revenue_prev=2880.0, net_profit=464.0,
                         net_profit_prev=455.0, ocf=150.2, gross_margin=None,
                         gross_margin_prev=None, expense_ratio=None, expense_ratio_prev=None),
    },
    "300750": {
        "2024年报": dict(revenue=3620.0, revenue_prev=4009.2, net_profit=507.5,
                         net_profit_prev=441.2, ocf=970.0, gross_margin=23.5,
                         gross_margin_prev=21.9, expense_ratio=9.8, expense_ratio_prev=9.5),
        "2023年报": dict(revenue=4009.2, revenue_prev=3285.9, net_profit=441.2,
                         net_profit_prev=307.3, ocf=928.3, gross_margin=21.9,
                         gross_margin_prev=20.3, expense_ratio=9.5, expense_ratio_prev=9.3),
    },
}

_DEMO_TEXT = {
    "600519": {
        "2024年报": (
            "报告期内，公司实现营业总收入 1505.60 亿元，同比增长 1.94%，"
            "归属于上市公司股东的净利润 862.30 亿元，同比增长 15.39%。"
            "经营活动产生的现金流量净额为 745.20 亿元。"
            "公司毛利率保持稳定，产品结构持续优化，直销渠道收入占比进一步提升。"
            "管理层认为，白酒行业进入结构性调整期，公司将坚持稳中求进，"
            "适度扩大产能建设，持续提升品牌影响力。"
            "关于未来展望，公司未披露具体业绩目标。"
        ),
        "2023年报": (
            "报告期内，公司实现营业总收入 1476.90 亿元，同比增长 15.79%，"
            "归属于上市公司股东的净利润 747.30 亿元，同比增长 19.16%。"
            "经营活动产生的现金流量净额为 665.90 亿元。"
        ),
    },
    "000001": {
        "2024年报": (
            "报告期内，本行实现营业收入 3120.00 亿元，同比增长 3.62%；"
            "归属于本行股东的净利润 451.00 亿元，同比下降 2.80%。"
            "经营活动产生的现金流量净额为 120.50 亿元，同比大幅下降。"
            "本行加大不良资产处置力度，信用减值损失同比上升。"
            "管理层表示，经营情况总体稳健，将继续推进零售转型。"
        ),
        "2023年报": (
            "报告期内，本行实现营业收入 3011.00 亿元，同比增长 4.55%；"
            "归属于本行股东的净利润 464.00 亿元，同比增长 1.98%。"
        ),
    },
    "300750": {
        "2024年报": (
            "报告期内，公司实现营业总收入 3620.00 亿元，同比下降 9.71%；"
            "归属于上市公司股东的净利润 507.50 亿元，同比增长 15.02%。"
            "经营活动产生的现金流量净额为 970.00 亿元。"
            "公司毛利率较上年提升 1.6 个百分点，主要受益于原材料成本下降。"
            "管理层表示，动力电池行业竞争加剧，价格下行压力较大，"
            "公司将通过技术降本和海外产能释放对冲影响。"
        ),
        "2023年报": (
            "报告期内，公司实现营业总收入 4009.20 亿元，同比增长 22.01%；"
            "归属于上市公司股东的净利润 441.20 亿元，同比增长 43.58%。"
        ),
    },
}


def _current_mode() -> str:
    mode = os.getenv("DATA_MODE", MODE_AUTO).strip().lower()
    return mode if mode in (MODE_DEMO, MODE_AUTO, MODE_REAL) else MODE_AUTO


def fetch_financial_data(stock_code: str, report_period: str) -> FinData:
    """获取财务指标。返回对象 is_demo 标记数据真实性。"""
    mode = _current_mode()
    if mode == MODE_DEMO:
        return _demo_fin(stock_code, report_period)

    real = _call_fuyao(stock_code, report_period)
    if real is not None:
        return real
    if mode == MODE_REAL:
        raise RuntimeError("扶摇接口调用失败，DATA_MODE=real 下不降级，拒绝生成结论。")
    return _demo_fin(stock_code, report_period)


def fetch_report_text(stock_code: str, report_period: str) -> ReportText:
    """获取财报文本片段。

    真实财务数据可用但文本源缺失时，返回空文本 + 显式降级说明
    （由检查器提示「未执行文本-数字校验」，绝不静默生成结论）。
    """
    mode = _current_mode()
    if mode == MODE_DEMO:
        return _demo_text(stock_code, report_period)
    real = _call_ifind(stock_code, report_period)
    if real is not None:
        return real
    if mode == MODE_REAL:
        raise RuntimeError("iFinD 接口调用失败，DATA_MODE=real 下不降级，拒绝生成结论。")
    try:
        return _demo_text(stock_code, report_period)
    except KeyError:
        return ReportText(
            is_demo=False, stock_code=stock_code, report_period=report_period,
            text="",
            source="iFinD 未接入且演示库无对应文本，文本-数字校验不可用",
        )


# ============ 真实接口：扶摇 ============

def _call_fuyao(stock_code: str, report_period: str) -> Optional[FinData]:
    api_key = os.getenv("FUYAO_API_KEY", "").strip()
    if not api_key:
        return None
    headers = {"X-api-key": api_key}
    try:
        thscode = _thscode_of(stock_code)
        year = _year_of(report_period)

        # 1) 利润表：最近 6 期年报
        r1 = requests.get(
            f"{FUYAO_BASE}/api/a-share/financials/income-statements",
            params={"thscode": thscode, "period": "annual", "limit": 6},
            headers=headers, timeout=25,
        )
        r1.raise_for_status()
        j1 = r1.json()
        if j1.get("code") != 0:
            if j1.get("code") == 1002:  # Unknown thscode：标的无效或无数据
                raise KeyError(f"未找到股票 {stock_code}（{thscode}）")
            raise RuntimeError(f"扶摇利润表接口返回错误：code={j1.get('code')} msg={j1.get('message')}")
        items1 = j1.get("data", {}).get("item", [])
        cur = _pick_fy(items1, year)
        if cur is None:
            raise KeyError(f"{stock_code} {report_period} 无财务报表数据（可查最近年报）")
        prev = _pick_fy(items1, year - 1)

        # 2) 现金流量表：取目标期经营现金流
        r2 = requests.get(
            f"{FUYAO_BASE}/api/a-share/financials/cash-flow-statements",
            params={"thscode": thscode, "period": "annual", "limit": 6},
            headers=headers, timeout=25,
        )
        r2.raise_for_status()
        j2 = r2.json()
        if j2.get("code") != 0:
            if j2.get("code") == 1002:
                raise KeyError(f"未找到股票 {stock_code}（{thscode}）")
            raise RuntimeError(f"扶摇现金流量表接口返回错误：code={j2.get('code')} msg={j2.get('message')}")
        items2 = j2.get("data", {}).get("item", [])
        ocf_cur = _pick_fy(items2, year, "act_cash_flow_net")

        return _map_fuyao_fin(stock_code, report_period, cur, prev, ocf_cur, j1.get("request_id", ""))
    except requests.RequestException as exc:
        print(f"[fetch] fuyao request failed: {exc}")
        return None
    except KeyError:
        raise
    except RuntimeError:
        raise


def _map_fuyao_fin(
    stock_code: str, report_period: str,
    cur: dict, prev: Optional[dict], ocf_cur: Optional[float], request_id: str,
) -> FinData:
    """扶摇字段 -> FinData。金额原币元 -> 亿元（除以 1e8）。"""
    YI = 1e8

    def to_yi(v):
        return round(v / YI, 2) if v is not None else None

    rev = to_yi(cur.get("operating_income"))
    rev_prev = to_yi(prev.get("operating_income")) if prev else None
    np_ = to_yi(cur.get("parent_holder_net_profit") or cur.get("net_profit"))
    np_prev = to_yi(prev.get("parent_holder_net_profit") or prev.get("net_profit")) if prev else None
    ocf = to_yi(ocf_cur)

    def _margin(row: dict) -> Optional[float]:
        oi = row.get("operating_income")
        if oi:
            return round((oi - (row.get("operating_costs") or 0)) / oi * 100, 2)
        return None

    def _expense(row: dict) -> Optional[float]:
        oi = row.get("operating_income")
        if oi:
            return round(((row.get("sales_fee") or 0) + (row.get("manage_fee") or 0)) / oi * 100, 2)
        return None

    as_of = ""
    if cur.get("period_end_ms"):
        as_of = datetime.fromtimestamp(cur["period_end_ms"] / 1000, CN_TZ).strftime("%Y-%m-%d")

    return FinData(
        is_demo=False, stock_code=stock_code, report_period=report_period,
        as_of=as_of,
        revenue=rev, revenue_prev=rev_prev,
        net_profit=np_, net_profit_prev=np_prev,
        ocf=ocf,
        gross_margin=_margin(cur), gross_margin_prev=_margin(prev) if prev else None,
        expense_ratio=_expense(cur), expense_ratio_prev=_expense(prev) if prev else None,
        source=f"扶摇 A股财务报表 API（同花顺）request_id={request_id}；时点 {as_of}；口径：亿元/百分比",
        raw={"cur": cur, "prev": prev},
    )


def _call_ifind(stock_code: str, report_period: str) -> Optional[ReportText]:
    """通过 iFinD MCP（search_notice）获取目标报告期年报的公告文本片段。"""
    client = _get_ifind_client()
    if not client.available():
        return None
    try:
        year = _year_of(report_period)
        # 年报在次年披露；公告检索区间取披露年全年
        time_start = f"{year + 1}-01-01"
        time_end = f"{year + 1}-12-31"
        query = f"{stock_code} {year}年年度报告 管理层讨论与分析 经营情况讨论与分析 主要经营情况"
        pieces = client.search_notice(query, size=3, time_start=time_start, time_end=time_end)
        if not pieces:
            return None
        return ReportText(
            is_demo=False, stock_code=stock_code, report_period=report_period,
            text="\n".join(pieces),
            source=f"iFinD MCP（同花顺公告 search_notice），检索区间 {time_start}~{time_end}",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[fetch] ifind failed: {exc}")
        return None


_ifind_client: Optional[IFindMCPClient] = None


def _get_ifind_client() -> IFindMCPClient:
    global _ifind_client
    if _ifind_client is None:
        from .mcp_client import IFindMCPClient
        _ifind_client = IFindMCPClient()
    return _ifind_client


# ============ 演示数据 ============

def _demo_fin(stock_code: str, report_period: str) -> FinData:
    stock = _DEMO_FIN.get(stock_code)
    if stock is None or report_period not in stock:
        raise KeyError(f"演示库中无 {stock_code} {report_period} 数据")
    row = stock[report_period]
    return FinData(
        is_demo=True, stock_code=stock_code, report_period=report_period,
        as_of="2026-09-18",
        revenue=row["revenue"], revenue_prev=row["revenue_prev"],
        net_profit=row["net_profit"], net_profit_prev=row["net_profit_prev"],
        ocf=row["ocf"], gross_margin=row["gross_margin"],
        gross_margin_prev=row["gross_margin_prev"],
        expense_ratio=row["expense_ratio"], expense_ratio_prev=row["expense_ratio_prev"],
        source="内置构造演示数据（非真实财报，仅用于评审演示）",
        raw=row,
    )


def _demo_text(stock_code: str, report_period: str) -> ReportText:
    stock = _DEMO_TEXT.get(stock_code)
    if stock is None or report_period not in stock:
        raise KeyError(f"演示库中无 {stock_code} {report_period} 文本")
    return ReportText(
        is_demo=True, stock_code=stock_code, report_period=report_period,
        text=stock[report_period],
        source="内置构造演示文本（非真实财报，仅用于评审演示）",
    )
