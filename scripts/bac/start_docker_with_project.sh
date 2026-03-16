#!/usr/bin/env sh
# 按「当前项目路径」启动 Docker，将该项目目录挂载为容器内 /app/project。
# 使用方式：在项目根目录执行 ./scripts/start_docker_with_project.sh
# 当前项目路径来自：新建项目后由 API 写入的 .insar_current_project，或侧边栏选择项目后的 API 更新。

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/.insar_current_project"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "未找到当前项目配置。请先在前端「新建工程」或选择已有项目后再运行本脚本。"
  echo "配置文件路径: $CONFIG_FILE"
  exit 1
fi

PROJECT_PATH="$(cat "$CONFIG_FILE" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [ -z "$PROJECT_PATH" ]; then
  echo "当前项目路径为空。请先新建或选择项目。"
  exit 1
fi

if [ ! -d "$PROJECT_PATH" ]; then
  echo "项目路径不存在: $PROJECT_PATH"
  echo "请确认路径正确或重新选择项目。"
  exit 1
fi

echo "当前项目路径: $PROJECT_PATH"
echo "正在启动 Docker（该项目将挂载为容器内 /app/project）..."

export PROJECT_PATH
cd "$PROJECT_ROOT"
docker-compose --profile full up -d

echo "Docker 已启动。项目目录在容器内为 /app/project"
