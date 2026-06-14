# deploy.ps1 - One-click deploy: start LLM on Mac, then build Docker image
# Requires PowerShell 5.x+
#
# Usage:
#   .\deploy.ps1
#   .\deploy.ps1 -LlmHost 192.168.1.100   # override LLM_HOST in .env
#   .\deploy.ps1 -SkipLlm                 # skip LLM startup check

param(
    [string]$LlmHost = "",
    [switch]$SkipLlm
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# -- SSH config (Mac) --------------------------------------------------
$SSH_KEY  = "C:\Users\Peng\Desktop\LocalLLM\id_rsa"
$SSH_USER = "peng"
$SSH_HOST = "LocalLLM"
$LLM_SCRIPTS = "~/llm-scripts"

$MODEL_SCRIPT_MAP = @{
    "qwen3.6-27b"        = "start-27b-ImageInputUnsupported.sh"
    "qwen3.6-27b-vision" = "start-27b-ImageInputSupported.sh"
    "qwen3.6-35b"        = "start-35b-ImageInputUnsupported.sh"
    "qwen3.6-35b-vision" = "start-35b-ImageInputSupported.sh"
    "qwen3.6-uncensored" = "start-uncensored.sh"
}

Write-Host "=== Orchestrator Deploy ===" -ForegroundColor Cyan

# -- Handle .env -------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
} else {
    Write-Host ".env already exists, skipping" -ForegroundColor Gray
}

if ($LlmHost -ne "") {
    (Get-Content ".env") -replace '^LLM_HOST=.*', "LLM_HOST=$LlmHost" | Set-Content ".env"
    Write-Host "Updated LLM_HOST to $LlmHost" -ForegroundColor Green
}

# Read .env variables
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

# -- Start LLM on Mac --------------------------------------------------
if (-not $SkipLlm) {
    Write-Host ""
    Write-Host "Checking LLM on Mac (port $llmPort)..." -ForegroundColor Cyan

    $sshOpts = @("-i", $SSH_KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", "${SSH_USER}@${SSH_HOST}")

    $listening = & ssh @sshOpts "lsof -ti :$llmPort" 2>$null
    if ($listening) {
        Write-Host "LLM already running (PID $($listening.Trim())), skipping." -ForegroundColor Green
    } else {
        if ($MODEL_SCRIPT_MAP.ContainsKey($llmModel)) {
            $script     = $MODEL_SCRIPT_MAP[$llmModel]
            $scriptPath = "$LLM_SCRIPTS/$script"
            Write-Host "Starting LLM: $scriptPath" -ForegroundColor Yellow

            # Build remote command as array to avoid PS parsing > and &
            $sshOptsNoTimeout = @("-i", $SSH_KEY, "-o", "StrictHostKeyChecking=no", "${SSH_USER}@${SSH_HOST}")
            $remoteCmd = "nohup $scriptPath > ~/llm.log 2>&1 &"
            & ssh @sshOptsNoTimeout $remoteCmd

            Write-Host "Waiting for LLM (up to 120s)" -NoNewline -ForegroundColor Cyan
            $ready = $false
            for ($i = 0; $i -lt 24; $i++) {
                Start-Sleep -Seconds 5
                Write-Host "." -NoNewline -ForegroundColor Cyan
                $check = & ssh @sshOptsNoTimeout "curl -sf http://localhost:${llmPort}/v1/models" 2>$null
                if ($check) {
                    $ready = $true
                    break
                }
            }
            Write-Host ""
            if ($ready) {
                Write-Host "LLM is ready!" -ForegroundColor Green
            } else {
                Write-Host "WARNING: LLM not ready after 120s, continuing anyway." -ForegroundColor Yellow
                Write-Host "Check logs: ssh -i $SSH_KEY peng@LocalLLM tail -f ~/llm.log" -ForegroundColor Gray
            }
        } else {
            Write-Host "WARNING: No startup script found for model '$llmModel', skipping LLM start." -ForegroundColor Yellow
        }
    }
}

# -- Build Docker image ------------------------------------------------
Write-Host ""
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker compose build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "=== Deploy complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Run orchestrator:" -ForegroundColor Cyan
Write-Host "  docker compose run --rm orchestrator python main.py --project /projects/btc-quant" -ForegroundColor White
Write-Host ""
Write-Host "Other commands:" -ForegroundColor Cyan
Write-Host "  Switch project : docker compose run --rm orchestrator python main.py --project /projects/c2-research"
Write-Host "  Switch model   : `$env:LLM_MODEL='qwen3.6-35b'; docker compose run --rm orchestrator python main.py --project /projects/btc-quant"
Write-Host "  Update Mac IP  : .\deploy.ps1 -LlmHost 192.168.x.x"
Write-Host "  Skip LLM check : .\deploy.ps1 -SkipLlm"
Write-Host "  View LLM logs  : ssh -i $SSH_KEY peng@LocalLLM tail -f ~/llm.log"
