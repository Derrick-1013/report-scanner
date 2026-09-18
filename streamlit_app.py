# -*- coding: utf-8 -*-
"""财报疑点放大镜 —— Streamlit 入口（用于 Streamlit Community Cloud 免费托管）。

本地运行：streamlit run streamlit_app.py
云端部署：GitHub 仓库 → share.streamlit.io → New app → 选本仓库 main 分支
环境变量在 Streamlit 的 Secrets 里配置（Settings → Secrets）：
  FUYAO_API_KEY / IFIND_MCP_URL / IFIND_MCP_AUTH / DATA_MODE
"""
from __future__ import annotations

import os
import sys

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# 从 Streamlit Secrets 注入环境变量（云端），本地 .env 也兼容
try:
    for k, v in st.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()

from agent import checks, fetch
from agent.llm import LLMClient

st.set_page_config(page_title="财报疑点放大镜", page_icon="🔍", layout="wide")

st.title("🔍 财报疑点放大镜")
st.caption("输入 A 股代码与报告期，AI 定位财报疑点并锚定原文证据 —— 只陈列事实，不构成投资建议。")

with st.sidebar:
    st.header("输入")
    stock = st.text_input("股票代码（A股 6 位）", value="600519", max_chars=6)
    period = st.text_input("报告期", value="2025年报", max_chars=16)
    run_btn = st.button("开始审查", type="primary", use_container_width=True)
    st.divider()
    st.caption("数据来源：扶摇财务 API + iFinD 公告文本。本产品仅做疑点筛查，不预测股价、不提供买卖建议。")

if run_btn:
    if not stock.strip() or not period.strip():
        st.error("请填写股票代码和报告期。")
    elif not stock.strip().isdigit() or len(stock.strip()) != 6:
        st.error("股票代码需为 6 位数字，例如 600519。")
    else:
        with st.spinner("正在取数并审查……"):
            try:
                fin = fetch.fetch_financial_data(stock.strip(), period.strip())
            except KeyError as e:
                st.error(f"未找到 {stock} {period} 的财务数据，无法执行审查。")
                st.stop()
            except RuntimeError as e:
                st.error(str(e))
                st.stop()

            try:
                text = fetch.fetch_report_text(stock.strip(), period.strip())
            except RuntimeError as e:
                st.warning(f"公告文本获取失败：{e}（仅完成数值与勾稽检查）")
                from agent.fetch import ReportText
                text = ReportText(text="", source="", is_demo=True)

            llm = LLMClient()
            result = checks.run_all(fin, text, llm)

        st.subheader("审查结果")
        st.info(f"数据模式：{result['mode_note']}")
        for n in result["notes"]:
            st.caption(f"• {n}")

        evs = result["evidence"]
        if not evs:
            st.success("未识别出明显疑点。")
        else:
            st.markdown(f"**疑点清单（{len(evs)} 条）**")
            for e in evs:
                with st.container(border=True):
                    tag_color = {"事实确认": "🟢", "需要人工复核": "🟡", "仅推测": "🔴"}.get(e.get("tag", ""), "⚪")
                    st.markdown(f"### {tag_color} {e.get('title','')}  \n**标签：{e.get('tag','')}**")
                    st.write(e.get("detail", ""))
                    if e.get("quote"):
                        st.markdown(f"> **原文证据**：{e['quote']}")
                    st.caption(f"指标：{e.get('metric','')} ｜ 基准：{e.get('basis','')} ｜ 来源：{e.get('source','')}")

        st.divider()
        st.caption("所有结论请务必结合原文与人工复核后使用。市场有风险，投资需谨慎。")
