# 财报疑点放大镜｜AI‑Native 投资产品创新（题目 14）

> 为 A 股初级研究员与深度个人投资者，把「人工翻阅财报找异常」变成「AI 定位疑点 + 锚定原文证据 + 人工复核」。只陈列事实，不输出投资建议。



***

## 1. 产品简介



* **目标用户**：A 股买方 / 卖方初级研究员、个人深度投资者。

* **解决的痛点**：传统金融工具只展示财务数字，不做跨期对比与文本‑数字交叉校验；人工审阅年报季报耗时；普通搜索无法判断「管理层描述与报表数字是否矛盾」。

* **非目标**：不做舞弊定性、不输出股价预测、不提供任何投资买卖建议、不覆盖港股美股。

## 2. 为什么需要 LLM / Agent（AI 增量价值）



1. **规则系统做不到语义判断**：规则只能配置固定阈值（如营收变动 > 30%），无法处理「风险披露是否含糊」「管理层说辞与报表数字是否冲突」这类软逻辑。

2. **多工具调用（Agent）**：并行调用扶摇财务 API 与 iFinD MCP 财报文本，把「数字」与「文本」两个异构来源串成一条证据链。

3. **软推理与证据分级**：区分【事实确认】/【需要人工复核】/【仅推测】，每条疑点绑定原文片段、来源、时点、口径。

4. **人机协作闭环**：用户对疑点标记「确认 / AI 误报」，反馈回灌到后续分析上下文，持续校准输出。

5. **失败降级**：数据缺失或接口失败时明确提示，绝不静默生成「正常」结论。

## 3. 核心工作流



```
输入股票代码 + 报告期

&#x20;       │

&#x20;       ▼

\[1] 取数：扶摇财务 API（指标）＋ iFinD MCP（财报文本片段）

&#x20;       │

&#x20;       ▼

\[2] 三类检查

&#x20;  ├─ 数值异常：营收/净利同比跳变（±30%）、毛利率波动（±5pct）、费用率变化（±3pct）

&#x20;  ├─ 勾稽疑点：净利润与经营现金流背离（现金流/净利 < 0.7）

&#x20;  └─ 文本‑数字一致性（LLM）：MD\&A 描述与数字矛盾、表述含糊

&#x20;       │

&#x20;       ▼

\[3] 输出疑点清单：指标、对比基准、原文引用、来源、置信标签

&#x20;       │

&#x20;       ▼

\[4] 用户反馈：确认疑点 / 标记 AI 误报（人机闭环）

&#x20;       │

&#x20;       ▼

\[5] 导出审查报告（含全部来源溯源）
```

## 4. AI 角色定义

财报审查 Agent —— 仅做**疑点识别与证据陈列**，不做好坏定性、不做风险评级，所有疑点交由人工复核。

**置信标签体系**（每条输出强制三选一）：



* `【事实确认】`：数据与原文直接匹配，属客观披露。

* `【需要人工复核】`：存在异常信号，但需结合业务二次确认。

* `【仅推测】`：AI 推断，无直接原文支撑，必须显著标注。

## 5. 数据来源



| 数据                                | 来源                          | 状态                                            |
| --------------------------------- | --------------------------- | --------------------------------------------- |
| 财务指标（营收 / 净利 / 经营现金流 / 毛利率 / 费用率） | 扶摇 A 股财务报表 API（利润表 + 现金流量表） | ✅ 已真实接入，`agent/fetch.py` 实现字段映射与 thscode 自动推断 |
| 财报文本（公告 / 管理层讨论） | iFinD MCP（`search_notice` 公告语义查询） | ✅ 已接入，`agent/mcp_client.py`（streamable HTTP 客户端） |
| LLM（文本校验） | OpenAI 兼容接口 | ⚠️ 配置 `LLM_API_KEY` 后启用；未配置时规则引擎模式运行 |

> **真实数据链路**
>
> （
>
> `fetch.py`
>
> ）：
> 利润表 
>
> `GET /api/a-share/financials/income-statements?thscode=600519.SH&period=annual&limit=6`
>
> ：取目标期与上一年，计算营收、归母净利、毛利率、销售 + 管理费用率（原币元→亿元）。
> 现金流量表 
>
> `GET /api/a-share/financials/cash-flow-statements`
>
> ：取目标期经营现金流。
> 财报文本（
>
> `agent/mcp_client.py`
>
> ）：iFinD MCP `search_notice`，按「代码 + 年份年报 + 管理层讨论」查询公告片段，检索区间取披露年全年（如 2025 年报 → 2026-01-01~2026-12-31）。
> thscode 自动推断（600/601/603/605/688→SH，000/001/002/003/300/301→SZ，其余→BJ）。
> 报告期解析：
>
> `2025年报`
>
> →2025 财年；只支持年报（
>
> `period=annual`
>
> ）。
> **数据模式（**
>
> `.env`
>
> **&#x20;中&#x20;**
>
> `DATA_MODE`
>
> **）**
>
> ：
> `demo`
>
> ：始终使用内置构造数据，页面与结果中明确标注「演示数据」—— 适合无密钥评审演示。
> `auto`
>
> （默认）：优先真实接口（需 
>
> `FUYAO_API_KEY`
>
> 与 
>
> `IFIND_MCP_URL/IFIND_MCP_AUTH`
>
> ），财务或文本源缺失时显式降级提示。
> `real`
>
> ：仅真实接口，财务 / 文本任一失败直接报错，不生成任何结论。

## 6. 成功标准与失败条件

### 可衡量成功标准



1. 输入合法股票代码 + 报告期，可返回疑点列表，每条疑点可溯源到原文片段。

2. 对存在已知异常指标的财报，能识别出对应疑点（如净利与现金流背离）。

3. 用户反馈（标记误报）可被系统接收并影响后续分析上下文。

### 失败条件（必须明确展示）



1. 股票代码不存在 / 该报告期无财报 → 返回明确错误信息，**不生成任何疑点**。

2. API 接口超时或调用失败 → 页面提示「数据获取失败」，**禁止 AI 编造数据**。

3. 财报文本缺失 → 明确提示仅完成数值与勾稽检查，不做文本‑数字校验。

## 7. 合规边界（硬约束）



1. 不输出确定性涨跌预测、收益承诺或直接买卖建议。

2. 事实 / 疑点 / 推测严格区分，推测必须显著标注。

3. 核心结论必须回到原始字段或原文，明确来源、时点、单位、口径。

4. 数据缺失、冲突、过期或调用失败时，不得静默生成「正常」结论。

5. 公开仓库不含任何真实 API Key（见 `.gitignore`，密钥只放本地 `.env`）。

## 8. 已知边界与未做事项

### 已知边界



1. 依赖数据接口质量；接口返回截断文本会导致部分校验失效。

2. Agent 基于 Prompt 工程实现，未做模型微调，存在 AI 幻觉与误报可能。

3. 不支持财报 PDF / 图片内容解析，仅处理接口返回文本片段。

4. 演示库仅覆盖 3 只标的、2 个报告期。

### 未做事项



1. 未实现全量 PDF 本地解析。

2. 未实现用户账号系统；人机反馈仅存内存，服务重启后清空。

3. 未实现大规模批量扫描，仅支持单只股票单期查询。

4. 文本 - 数字一致性校验需配置 `LLM_API_KEY` 才能完整运行（iFinD 财报文本已接入）；未配置时该维度显式降级。

5. 报告期仅支持年报（`period=annual`），季报 / 中报未接入。

## 9. 启动方式



```
\# 1. 安装依赖

pip install -r requirements.txt

\# 2. 配置环境变量

copy .env.example .env

\# 编辑 .env 填入密钥；不填也能以 demo 模式运行

\# 3. 启动

uvicorn main:app --host 0.0.0.0 --port 8000

\# 或

python main.py

\# 4. 浏览器访问

http://localhost:8000
```

## 10. 部署为公网可访问 URL（评审要求）
> Windows 用户可直接使用仓库内 `deploy.ps1`（`.\deploy.ps1 -Local` 本地运行、`-GitInit` 初始化、`-PushHF -HfUser <用户名>` 推送 HuggingFace、`-PushGithub -RepoUrl <url>` 推送 GitHub）。
> 推送前请确认 `.env` 不会被带上（已由 `.gitignore` / `.dockerignore` 排除）。

### 方案 A：HuggingFace Spaces（推荐，免费且稳定）

1. 注册并登录 https://huggingface.co → 右上角 **+ New Space**
2. 配置：Space name 填 `report-scanner`，License 选 MIT，**SDK 选 Docker**，Public 公开 → Create Space
3. 本机推送代码（需已安装 git）：
   ```bash
   cd report-scanner
   git init
   git add .
   git commit -m "init"
   git remote add origin https://huggingface.co/spaces/<你的用户名>/report-scanner
   git push -u origin main
   ```
4. Space 页面 → **Settings → Variables and secrets** 添加：
   - `FUYAO_API_KEY` = 你的扶摇 key
   - `DATA_MODE` = `auto`
5. 等待自动构建（约 1–3 分钟），完成后访问 `https://<你的用户名>-report-scanner.hf.space`

### 方案 B：Replit（导入 GitHub 仓库）

1. 先把仓库推到 GitHub（见下节）
2. replit.com → Create Repl → **Import from GitHub** → 选该仓库
3. 左侧 **Tools → Secrets** 添加 `FUYAO_API_KEY` 与 `DATA_MODE=auto`
4. Shell 执行：`pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 3000`

### 方案 C：ngrok 本地临时（最快，但需保持电脑开机）

```bash
winget install ngrok
ngrok config add-authtoken <你的ngrok-token>   # 官网注册免费获取
uvicorn main:app --host 0.0.0.0 --port 8000
ngrok http 8000
```

- **禁止**只提交 `localhost` 地址；ngrok 地址重启会变，请保证评审期间可用。

## 11. 目录结构



```
report-scanner/

├── main.py              # FastAPI 入口 + API + 静态页

├── requirements.txt

├── .env.example         # 环境变量样例（真实密钥勿提交）

├── .gitignore

├── agent/

│   ├── \_\_init\_\_.py

│   ├── fetch.py         # 数据获取（扶摇/iFinD + 演示数据 + 失败降级）

│   ├── checks.py        # 三类检查器（数值/勾稽/文本‑数字）

│   ├── evidence.py      # 证据模型与置信标签

│   ├── llm.py           # OpenAI 兼容 LLM 客户端
│   └── mcp_client.py    # iFinD MCP 客户端（streamable HTTP / search_notice）

├── frontend/

│   └── index.html       # 单页前端（表单/卡片/反馈/导出）

├── tests/

│   └── test\_case.md     # 测试说明（必交）

└── docs/

&#x20;   └── ai\_validation\_record.md  # AI 使用与验证记录（必交）
```

## 12. 后续验证计划



1. 扩充测试样本集，收集研究员标注，统计 AI 误报率 / 召回率。

2. 针对高频误报优化 Prompt 与阈值。

3. 接入真实扶摇 /iFinD 数据，做真实财报的端到端校验。

4. 增加更多勾稽规则（应收 / 存货占比、商誉减值等）。

## 免责声明

本工具仅用于研究学习与演示，所有输出仅供参考，不构成任何投资建议。市场有风险，投资需谨慎。