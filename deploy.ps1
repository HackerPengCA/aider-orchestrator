# deploy.ps1 — Windows PowerShell 一键部署脚本
# LLM 运行在局域网 Mac 上，通过 SSH 自动启动后再部署容器
#
# 用法：
#   .\deploy.ps1
#   .\deploy.ps1 -LlmHost 192.168.1.100   # 覆盖 .env 里的 LLM_HOST
#   .\deploy.ps1 -SkipLlm                 # 跳过 LLM 启动检查

param(
    [string]$LlmHost = "",
    [switch]$SkipLlm
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

# ── SSH 配置（Mac 固定，通常不需要改）──────────────────────
$SSH_KEY  = "C:\Users\Peng\Desktop\LocalLLM\id_rsa"
$SSH_USER = "peng"
$SSH_HOST = "LocalLLM"          # Bonjour hostname，Windows 侧 SSH 可用
$LLM_SCRIPTS_DIR = "~/llm-scripts"

# model alias → 启动脚本 映射
$MODEL_SCRIPT_MAP = @{
    "qwen3.6-27b"          = "start-27b-ImageInputUnsupported.sh"
    "qwen3.6-27b-vision"   = "start-27b-ImageInputSupported.sh"
    "qwen3.6-35b"          = "start-35b-ImageInputUnsupported.sh"
    "qwen3.6-35b-vision"   = "start-35b-ImageInputSupported.sh"
    "qwen3.6-uncensored"   = "start-uncensored.sh"
}

Write-Host "=== Orchestrator 一键部署 ===" -ForegroundColor Cyan

# ── 处理 .env ──────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env（从 .env.example 复制）" -ForegroundColor Yellow
} else {
    Write-Host ".env 已存在，跳过创建" -ForegroundColor Gray
}

if ($LlmHost -ne "") {
    (Get-Content ".env") -replace '^LLM_HOST=.*', "LLM_HOST=$LlmHost" | Set-Content ".env"
    Write-Host "已更新 LLM_HOST 为 $LlmHost" -ForegroundColor Green
}

# 读取 .env 变量
$envVars = @{}
Get-Content ".env" | Where-Object { $_ -match '^[^#].*=.*' } | ForEach-Object {
    $parts = $_ -split '=', 2
    $envVars[$parts[0].Trim()] = $parts[1].Trim()
}
$llmPort  = $envVars["LLM_PORT"]  ?? "8081"
$llmModel = $envVars["LLM_MODEL"] ?? "qwen3.6-27b"

Write-Host "LLM_HOST  = $($envVars['LLM_HOST'])" -ForegroundColor Cyan
Write-Host "LLM_PORT  = $llmPort" -ForegroundColor Cyan
Write-Host "LLM_MODEL = $llmModel" -ForegroundColor Cyan

# ── 启动 Mac 上的 LLM ──────────────────────────────────────
if (-not $SkipLlm) {
    Write-Host ""
    Write-Host "正在检查 Mac 上的 LLM（port $llmPort）..." -ForegroundColor Cyan

    $sshBase = "ssh -i `"$SSH_KEY`" -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${SSH_USER}@${SSH_HOST}"

    # 检查端口是否已在监听
    $listening = Invoke-Expression "$sshBase `"lsof -ti :$llmPort`"" 2>$null
    if ($listening) {
        Write-Host "LLM 已在运行（PID $($listening.Trim())），跳过启动。" -ForegroundColor Green
    } else {
        # 查找对应启动脚本
        $script = $MODEL_SCRIPT_MAP[$llmModel]
        if (-not $script) {
            Write-Host "⚠ 未找到模型 '$llmModel' 对应的启动脚本，跳过 LLM 启动。" -ForegroundColor Yellow
            Write-Host "  请手动在 Mac 上启动 llama.cpp，或在 MODEL_SCRIPT_MAP 里补充映射。" -ForegroundColor Gray
        } else {
            $scriptPath = "$LLM_SCRIPTS_DIR/$script"
            Write-Host "启动 LLM：$scriptPath" -ForegroundColor Yellow
            Invoke-Expression "$sshBase `"nohup $scriptPath > ~/llm.log 2>&1 &`""

            # 等待 LLM 就绪（最多 120 秒）
            Write-Host "等待 LLM 就绪" -NoNewline -ForegroundColor Cyan
            $ready = $false
            for ($i = 0; $i -lt 24; $i++) {
                Start-Sleep -Seconds 5
                Write-Host "." -NoNewline -ForegroundColor Cyan
                $check = Invoke-Expression "$sshBase `"curl -sf http://localhost:${llmPort}/v1/models`"" 2>$null
                if ($check) { $ready = $true; break }
            }
            Write-Host ""
            if ($ready) {
                Write-Host "LLM 已就绪！" -ForegroundColor Green
            } else {
                Write-Host "⚠ LLM 120 秒内未就绪，继续部署，稍后可手动确认。" -ForegroundColor Yellow
                Write-Host "  Mac 上查看日志：tail -f ~/llm.log" -ForegroundColor Gray
            }
        }
    }
}

# ── 构建 Docker 镜像 ───────────────────────────────────────
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
Write-Host "启动 Orchestrator：" -ForegroundColor Cyan
Write-Host "  docker compose run --rm orchestrator python main.py --project /projects/btc-quant" -ForegroundColor White
Write-Host ""
Write-Host "其他命令：" -ForegroundColor Cyan
Write-Host "  临时切换模型：" -ForegroundColor Gray
Write-Host "    `$env:LLM_MODEL='qwen3.6-35b'; docker compose run --rm orchestrator python main.py --project /projects/btc-quant" -ForegroundColor White
Write-Host "  更新 Mac IP：" -ForegroundColor Gray
Write-Host "    .\deploy.ps1 -LlmHost 192.168.x.x" -ForegroundColor White
Write-Host "  跳过 LLM 启动检查：" -ForegroundColor Gray
Write-Host "    .\deploy.ps1 -SkipLlm" -ForegroundColor White
Write-Host "  查看 Mac LLM 日志：" -ForegroundColor Gray
Write-Host "    ssh -i C:\Users\Peng\Desktop\LocalLLM\id_rsa peng@LocalLLM tail -f ~/llm.log" -ForegroundColor White
