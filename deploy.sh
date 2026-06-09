#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Orchestrator 一键部署 ==="

# 首次部署：从模板生成 .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "已创建 .env（如需修改 LLM 地址请编辑后重新运行）"
else
    echo ".env 已存在，跳过创建"
fi

echo ""
echo "正在构建镜像..."
docker compose build

echo ""
echo "=== 部署完成 ==="
echo ""
echo "使用方式（在 LocalLLM/orchestrator/ 目录下运行）："
echo ""
echo "  qwen-code（交互式）:"
echo "    docker compose run --rm qwen-code"
echo ""
echo "  Orchestrator（自动化任务）:"
echo "    echo '/projects/btc-quant/task.md' | docker compose run --rm -T orchestrator python main.py --project /projects/btc-quant --yes"
echo ""
echo "  切换模型（临时）:"
echo "    LLM_MODEL=qwen3.6-35b docker compose run --rm qwen-code"
echo ""
echo "  如果 LLM 在其他机器，编辑 .env 修改 LLM_HOST，然后重新运行 deploy.sh"
