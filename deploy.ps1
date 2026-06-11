# deploy.ps1 — Windows PowerShell 一键部署脚本
# LLM 运行在局域网 Mac 上，通过 IP 远程调用
#
# 用法：
#   .\deploy.ps1
#   .\deploy.ps1 -LlmHost 192.168.1.100   # 直接指定 Mac IP

param(
    [string]$LlmHost = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 切换到脚本所在目录
Set-Location $PSScriptRoot

Write-Host "=== Orchestrator 一键部署 ===" -ForegroundColor Cyan

# ── 处理 .env ──────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env（从 .env.example 复制）" -ForegroundColor Yellow

    # 如果命令行传入了 IP，直接写入
    if ($LlmHost -ne "") {
        (Get-Content ".env") -replace '^LLM_HOST=.*', "LLM_HOST=$LlmHost" | Set-Content ".env"
        Write-Host "已将 LLM_HOST 设为 $LlmHost" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "⚠ 注意：LLM 运行在 Mac 上，请确认 .env 里的 LLM_HOST 是 Mac 的局域网 IP。" -ForegroundColor Yellow
        Write-Host "  Mac 上查看 IP：System Settings → Wi-Fi → Details，或 ifconfig | grep 'inet '" -ForegroundColor Gray
        Write-Host "  也可以重新运行：.\deploy.ps1 -LlmHost 192.168.x.x" -ForegroundColor Gray
    }
} else {
    Write-Host ".env 已存在，跳过创建" -ForegroundColor Gray

    # 如果传入了新 IP，更新现有 .env
    if ($LlmHost -ne "") {
        (Get-Content ".env") -replace '^LLM_HOST=.*', "LLM_HOST=$LlmHost" | Set-Content ".env"
        Write-Host "已更新 LLM_HOST 为 $LlmHost" -ForegroundColor Green
    }
}

# 显示当前 LLM_HOST 设置
$currentHost = (Get-Content ".env" | Select-String '^LLM_HOST=(.+)').Matches.Groups[1].Value
Write-Host "当前 LLM_HOST = $currentHost" -ForegroundColor Cyan

Write-Host ""
Write-Host "正在构建镜像..." -ForegroundColor Cyan
docker compose build
if ($LASTEXITCODE -ne 0) {
    Write-Host "构建失败，退出码 $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "=== 部署完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "使用方式（在 aider-orchestrator\ 目录下运行）：" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Orchestrator（自动化任务）:"
Write-Host "    Get-Content task.md | docker compose run --rm -T orchestrator python main.py --project /projects/btc-quant --yes" -ForegroundColor White
Write-Host ""
Write-Host "  临时切换模型："
Write-Host "    `$env:LLM_MODEL='qwen3.6-35b'; docker compose run --rm qwen-code" -ForegroundColor White
Write-Host ""
Write-Host "  切换 Mac 的 IP（重建不需要）："
Write-Host "    .\deploy.ps1 -LlmHost 192.168.x.x" -ForegroundColor White
