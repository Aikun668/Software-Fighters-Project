#!/usr/bin/env bash
# ===================================================================
#  Software-Fighters-Project 一键启动脚本（Git Bash / Agent 友好）
# -------------------------------------------------------------------
#  用法：
#    1. 用户:   ./start-all.sh
#    2. Agent:  bash start-all.sh
#
#  端口约定：
#    Python AI 服务  -> 8001
#    Java 后端       -> 8080
#    前端 dev server -> 5173
#
#  前置依赖（agent 跑前应已就绪）：
#    - MySQL 8.0 已运行且库表已初始化（sql/ 目录）
#    - Redis 7 已运行
#    - ai-service/.env 已填写 LLM API Key
#    - ai-service/venv 已存在（或系统 Python 装好了依赖）
#    - frontend/node_modules 已安装
# ===================================================================

set -u

# Windows 路径转 POSIX（脚本可能从 cmd 调过来）
ROOT="$(cd "$(dirname "$0")" && pwd)"
ROOT_WIN="$(cygpath -w "$ROOT" 2>/dev/null || echo "$ROOT")"

AI_DIR="$ROOT/ai-service"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

echo "=============================================================="
echo "  Software-Fighters-Project 一键启动"
echo "  ROOT = $ROOT"
echo "=============================================================="
echo ""

# --- 步骤 1: 启动 3 个服务到独立窗口（用 Windows 原生 start） ---
echo "[1/4] 启动 Python AI 服务 (窗口: AI-Service) ..."
cmd.exe /c start "AI-Service (8001)" cmd /k "cd /d \"${AI_DIR//\//\\}\" && python main.py"

echo "[2/4] 启动 Java 后端      (窗口: Java-Backend) ..."
cmd.exe /c start "Java-Backend (8080)" cmd /k "cd /d \"${BACKEND_DIR//\//\\}\" && mvnw.cmd spring-boot:run"

echo "[3/4] 启动前端 dev server  (窗口: Frontend) ..."
cmd.exe /c start "Frontend (5173)" cmd /k "cd /d \"${FRONTEND_DIR//\//\\}\" && pnpm dev"

echo ""
echo "[4/4] 等待服务就绪（最多 90s）..."

# --- 步骤 2: 健康检查（端口探测）---
wait_for_port() {
    local port=$1
    local name=$2
    local waited=0
    local max=90
    while [ "$waited" -lt "$max" ]; do
        # PowerShell 探测（Windows 上 nc 可能没装）
        if powershell -NoProfile -Command \
            "(Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)" \
            >/dev/null2>&1; then
            printf "      [+] :%-4d %s OK\n" "$port" "$name"
            return 0
        fi
        waited=$((waited + 5))
        printf "      [-] :%-4d %s 等待中... (t=%ds)\n" "$port" "$name" "$waited"
        sleep 5
    done
    printf "      [!] :%-4d %s 超时\n" "$port" "$name"
    return 1
}

ok_count=0
wait_for_port 8001 "AI-Service"  && ok_count=$((ok_count + 1)) || true
wait_for_port 8080 "Java-Backend" && ok_count=$((ok_count + 1)) || true
wait_for_port 5173 "Frontend"    && ok_count=$((ok_count + 1)) || true

echo ""
echo "=============================================================="
if [ "$ok_count" -eq 3 ]; then
    echo "  ✅ 3 个服务均已就绪"
    echo "    - AI  Service:  http://127.0.0.1:8001"
    echo "    - Java Backend: http://127.0.0.1:8080"
    echo "    - Frontend:    http://127.0.0.1:5173"
    echo "=============================================================="
    exit 0
else
    echo "  ⚠️ 只有 $ok_count/3 个服务就绪（SpringBoot 首次启动需 30-60s）"
    echo "    请到对应窗口查看启动日志"
    echo "=============================================================="
    exit 1
fi