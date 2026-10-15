#!/usr/bin/env bash
# 本地启动「投递简历智能体」服务（已去除 Coze 依赖，纯本地运行）
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PYTHONPATH="$PROJECT_ROOT/src:$PROJECT_ROOT"
export APP_MODE="${APP_MODE:-workflow}"
PORT="${PORT:-5000}"

# 加载项目根 .env（若存在），提供 ZHIPU_API_KEY 等
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

echo "==> 启动投递智能体 (mode=$APP_MODE, port=$PORT)"
cd "$PROJECT_ROOT/src"
exec python -m main -m http -p "$PORT"
