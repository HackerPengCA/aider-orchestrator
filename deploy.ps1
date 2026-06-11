# deploy.ps1 — Windows PowerShell 一键部署脚本（兼容 PS 5.x）
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

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ── SSH 配置 ────────────────────────────────────────────────
$SSH_KEY        = "C:\Users\Peng\Desktop\LocalLLM\id_rsa"
$SSH_USER       = "peng"
$SSH_HOST       = "LocalLLM"
$LLM_SCRIPTS    = "~/llm-scripts"

$MODEL_SCRIPT_MAP = @{
    "qwen3.6-27b"        = "start-27b-ImageInputUnsupported.sh"
    "qwen3.6-27b-vision" = "start-27b-ImageInputSupported.sh"
    "qwen3.6-35b"        = "start-35b-ImageInputUnsupported.sh"
    "qwen3.6-35b-vision" = "start-35b-ImageInputSupported.sh"
    "qwen3.6-uncensored" = "start-uncensored.sh"
}

Write-Host "=== Orchestrator 一键部署 ===" -ForegroundColor Cyan

# ── 处理 .env ──────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env" -ForegroundColor Yellow
} else {
    Write-Host ".env 已存在，跳过创建" -ForegroundColor Gray
}

if ($LlmHost -ne "") {
    (Get-Content ".env") -replace '^LLM_HOST=.*', "LLM_HOST=$LlmHost" | Set-Content ".env"
    Write-Host "已更新 LLM_HOST 为 $LlmHost" -ForegroundColor Green
}

# 读取 .env 变量
$envVars = @{}
Get-Content ".env" | Where-Object { $_ -match '^[^#].+=.+' } | ForEach-Object {
    $parts = $_ -split '=', 2
    $envVars[$parts[0].Trim()] = $parts[1].Trim()
}

if ($envVars.ContainsKey("LLM_PORT"))  { $llmPort  = $envVars["LLM_PORT"]  } else { $llmPort  = "8081" }
if ($envVars.ContainsKey("LLM_MODEL")) { $llmModel = $envVars["LLM_MODEL"] } else { $llmModel = "qwen3.6-27b" }
if ($envVars.ContainsKey("LLM_HOST"))  { $llmHostVal = $envVars["LLM_HOST"] } else { $llmHostVal = "?" }

Write-Host "LLM_HOST  = $llmHostVal" -ForegroundColor Cyan
Write-Host "LLM_PORT  = $llmPort"    -ForegroundColor Cyan
Write-Host "LLM_MODEL = $llmModel"   -ForegroundColor Cyan

# ── 启动 Mac 上的 LLM ──────────────────────────────────────
if (-not $SkipLlm) {
    Write-Host ""
    Write-Host "正在检查 Mac 上的 LLM（port $llmPort）..." -ForegroundColor Cyan

    $sshArgs = "-i `"$SSH_KEY`" -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${SSH_USER}@${SSH_HOST}"

    $listening = & ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 "${SSH_USER}@${SSH_HOST}" "lsof -ti :$llmPort" 2>$null

    if ($listening) {
        Write-Host "LLM 已在运行（PID $($listening.Trim())），跳过启动。" -ForegroundColor Green
    } else {
        if ($MODEL_SCRIPT_MAP.ContainsKey($llmModel)) {
            $script = $MODEL_SCRIPT_MAP[$llmModel]
            $scriptPath = "$LLM_SCRIPTS/$script"
            Write-Host "启动 LLM：$scriptPath" -ForegroundColor Yellow

            & ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${SSH_HOST}" "nohup $scriptPath > ~/llm.log 2>&1 &"

            Write-Host "等待 LLM 就绪（最多 120 秒）" -NoNewline -ForegroundColor Cyan
            $ready = $false
            for ($i = 0; $i -lt 24; $i++) {
                Start-Sleep -Seconds 5
                Write-Host "." -NoNewline -ForegroundColor Cyan
                $check = & ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${SSH_HOST}" "curl -sf http://localhost:${llmPort}/v1/models" 2>$null
                if ($check) {
                    $ready = $true
                    break
                }
            }
            Write-Host ""
            if ($ready) {
                Write-Host "LLM 已就绪！" -ForegroundColor Green
            } else {
                Write-Host "⚠ 120 秒内未就绪，继续部署。查看日志：" -ForegroundColor Yellow
                Write-Host "  ssh -i $SSH_KEY peng@LocalLLM tail -f ~/llm.log" -ForegroundColor Gray
            }
        } else {
            Write-Host "⚠ 未找到模型 '$llmModel' 的启动脚本，跳过 LLM 启动。" -ForegroundColor Yellow
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
Write-Host "    `$env:LLM_MODEL='qwen3.6-35b'; docker compose run --rm orchestrator python main.py --project /projects/c2-research" -ForegroundColor White
Write-Host "  更新 Mac IP：" -ForegroundColor Gray
Write-Host "    .\deploy.ps1 -LlmHost 192.168.x.x" -ForegroundColor White
Write-Host "  跳过 LLM 启动：" -ForegroundColor Gray
Write-Host "    .\deploy.ps1 -SkipLlm" -ForegroundColor White
Write-Host "  查看 Mac LLM 日志：" -ForegroundColor Gray
Write-Host "    ssh -i C:\Users\Peng\Desktop\LocalLLM\id_rsa peng@LocalLLM `"tail -f ~/llm.log`"" -ForegroundColor White
