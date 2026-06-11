# Aider Orchestrator

A lightweight autonomous coding agent that wraps [Aider](https://github.com/Aider-AI/aider) with a **Plan → Execute → Analyze → Loop** cycle, powered by a local LLM via llama.cpp.

## What it does

Instead of manually running Aider for each change, the Orchestrator:

1. Takes a high-level task description (text or file path)
2. Uses the LLM to generate an ordered execution plan
3. Executes each step — shell commands or Aider code generation
4. Feeds results back to the LLM to decide: next / retry / update plan / done
5. Loops until the task is complete

## Architecture

```
Windows machine (Docker Desktop)
  │
  ├── orchestrator container (main.py)
  │     ├── LLM Client (llm_client.py)   — streaming, plan & analysis
  │     ├── Sandbox (sandbox.py)         — security restrictions
  │     └── Executor (executor.py)
  │           ├── Shell commands         — run tests, scripts, installs
  │           └── Aider                  — write & modify code
  │
  └── HTTP → macOS (llama.cpp + Qwen3, LAN IP via LLM_HOST)
```

LLM config (`LLM_HOST`, `LLM_PORT`, `LLM_MODEL`) is read from `.env` at runtime — no image rebuild needed when switching models or hosts.

## Security Model

- **Write / Execute**: restricted to the specified project directory
- **Path traversal**: `../` escapes are blocked
- **Read**: unrestricted
- **Max retries per step**: 2 (configurable in `config.py`)
- **Command timeout**: 900s (configurable in `config.py`)

## Requirements

- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- llama.cpp running on a Mac (or any machine) with an OpenAI-compatible API

## Setup

```powershell
git clone https://github.com/HackerPengCA/aider-orchestrator
cd aider-orchestrator
.\deploy.ps1 -LlmHost 192.168.x.x   # Mac's LAN IP
```

`deploy.ps1` will:
1. Copy `.env.example` → `.env` (first run only) and write `LLM_HOST`
2. Run `docker compose build`

To find the Mac's IP:

```bash
# on Mac
ifconfig | grep 'inet ' | grep -v 127.0.0.1
# or: System Settings → Wi-Fi → Details
```

## Configuration

All LLM settings live in `.env` (gitignored). Edit it directly or re-run `deploy.ps1 -LlmHost`:

| Variable    | Default            | Description                                      |
|-------------|--------------------|--------------------------------------------------|
| `LLM_HOST`      | `host.docker.internal` | Mac/LAN IP where llama.cpp is running    |
| `LLM_PORT`      | `8081`             | llama.cpp `--port`                               |
| `LLM_MODEL`     | `qwen3.6-27b`      | Must match llama.cpp `--alias`                   |
| `PROJECTS_ROOT` | `C:/Users/Peng/Desktop/PersonalProjects` | Host path mounted at `/projects` |

## Usage

`PersonalProjects/` on the host is mounted at `/projects` inside the container. The `--project` flag takes the **container-side path**, e.g. `/projects/btc-quant` maps to `C:\Users\Peng\Desktop\PersonalProjects\btc-quant` on Windows.

### 方式一：run --rm（每次新容器，用完即删）

最干净，不留垃圾，适合偶尔跑一次的场景。

```powershell
docker compose run --rm orchestrator python main.py --project /projects/btc-quant
docker compose run --rm orchestrator python main.py --project /projects/c2-research
```

缺点：每次都要重新创建容器（慢几秒）。

### 方式二：run（不删容器，可以重启复用）

去掉 `--rm`，容器停止后保留在磁盘上，可以用 `docker start` 重新进入，省去重建开销。

```powershell
# 第一次运行（创建容器）
docker compose run orchestrator python main.py --project /projects/btc-quant

# 之后重启同一个容器（容器名查看：docker ps -a）
docker start -ai aider-orchestrator-orchestrator-1
```

缺点：停止的容器会慢慢堆积，需要手动 `docker rm` 清理。切换项目时也必须新建容器（因为 `--project` 是启动参数）。

### 方式三：up + exec（常驻容器，推荐日常使用）

容器在后台常驻，每次用 `exec` 直接进入执行，启动最快，切换项目也最方便。

```powershell
# 启动常驻容器（只需一次）
docker compose up -d

# 之后每次执行，直接 exec 进去
docker compose exec orchestrator python main.py --project /projects/btc-quant
docker compose exec orchestrator python main.py --project /projects/c2-research

# 停止常驻容器
docker compose down
```

缺点：容器一直在后台占用少量内存。

### 非交互模式（管道输入任务文件）

适合自动化或脚本调用，`--yes` 跳过确认。

```powershell
Get-Content task.md | docker compose run --rm -T orchestrator python main.py --project /projects/btc-quant --yes
```

### 临时切换模型

```powershell
$env:LLM_MODEL='qwen3.6-35b'; docker compose run --rm orchestrator python main.py --project /projects/btc-quant
```

### 任务输入格式

交互模式下，提示符支持直接输入文本或文件路径（自动读取内容）：

```
📝 输入任务或文件路径: /projects/c2-research/task.md
📝 输入任务或文件路径: Add a HTTP listener that beacons every 30s
```

## Key Design Decisions

**Streaming LLM calls** — Qwen3 runs in thinking mode and can take 10–60 minutes per response. Streaming keeps the connection alive regardless of how long the model thinks.

**No repo map** — `--map-tokens 0` disables Aider's project scan. Files are passed explicitly per step, keeping the prompt short and generation fast.

**Auto edit format** — Aider selects `whole` for new files and `diff` for existing ones. Forcing `diff` on a new file produces 0-byte output.

**Windows-aware commands** — The executor auto-translates Unix commands (`cat`→`type`, `ls`→`dir`, etc.) as a fallback. The LLM system prompt also instructs it to use Windows commands directly.

**Context passing** — Each step's output is accumulated and passed to subsequent analysis steps, so the LLM always has full context when making decisions.

## Tested With

- **Model**: Qwen3 27B / 35B via llama.cpp
- **LLM server**: macOS, llama.cpp with OpenAI-compatible API
- **Client**: Windows 11, Docker Desktop

## License

MIT
