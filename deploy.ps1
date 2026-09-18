# 财报疑点放大镜 - 部署辅助脚本（Windows PowerShell）
#
# 用法（在本目录下执行）：
#   1) 本地运行        .\deploy.ps1 -Local
#   2) 初始化 git 仓库  .\deploy.ps1 -GitInit
#   3) 推送 HuggingFace .\deploy.ps1 -PushHF -HfUser <你的HF用户名>
#   4) 推送 GitHub      .\deploy.ps1 -PushGithub -RepoUrl <你的GitHub仓库URL>
#
# 前提：已安装 git；已把 .env.example 复制为 .env 并填入密钥。
# 注意：.env 已被 .gitignore/.dockerignore 排除，不会随代码推送。

param(
    [switch]$Local,
    [switch]$GitInit,
    [string]$HfUser = "",
    [string]$RepoUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Check-Env {
    if (-not (Test-Path (Join-Path $Root ".env"))) {
        Write-Host "[warn] 未找到 .env，请先: Copy-Item .env.example .env 并填入密钥" -ForegroundColor Yellow
    } else {
        Write-Host "[ok] .env 存在（仅本机使用，不会被推送）" -ForegroundColor Green
    }
}

if ($Local) {
    Check-Env
    Write-Host "[run] uvicorn main:app --host 0.0.0.0 --port 8000" -ForegroundColor Cyan
    Set-Location $Root
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
    exit 0
}

if ($GitInit) {
    Check-Env
    Set-Location $Root
    if (Test-Path ".git") { Write-Host "[skip] 已是 git 仓库" }
    else {
        git init
        git add .
        git commit -m "财报疑点放大镜：AI-Native 投资产品（题目14）"
        Write-Host "[ok] git 仓库已初始化并提交" -ForegroundColor Green
    }
    exit 0
}

if ($HfUser) {
    Check-Env
    Set-Location $Root
    if (-not (Test-Path ".git")) { git init; git add .; git commit -m "财报疑点放大镜（题目14）" }
    $remote = "https://huggingface.co/spaces/$HfUser/report-scanner"
    if (-not (git remote | Select-String "origin")) { git remote add origin $remote }
    git push -u origin main
    Write-Host "[ok] 已推送到 HuggingFace Space。下一步在 Space 的 Settings -> Variables and secrets 配置："
    Write-Host "      FUYAO_API_KEY / IFIND_MCP_URL / IFIND_MCP_AUTH / DATA_MODE=auto" -ForegroundColor Cyan
    exit 0
}

if ($RepoUrl) {
    Check-Env
    Set-Location $Root
    if (-not (Test-Path ".git")) { git init; git add .; git commit -m "财报疑点放大镜（题目14）" }
    if (-not (git remote | Select-String "origin")) { git remote add origin $RepoUrl }
    git push -u origin main
    Write-Host "[ok] 已推送到 $RepoUrl" -ForegroundColor Green
    exit 0
}

Write-Host "用法见脚本头部注释。" -ForegroundColor Yellow
