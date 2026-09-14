#!/usr/bin/env bash
# ===================================================================
#  Spring Boot 后端一键重启脚本（Git Bash / Agent 友好）
# -------------------------------------------------------------------
#  适用场景：
#    - application.yml 改动后需要重启
#    - Java 代码改动后需要重启
#    - 8080 端口被老进程占用无法启动新进程
#    - Ctrl+C 没杀干净 javaw.exe
#
#  用法：
#    1. 用户:   ./restart.sh
#    2. Agent:  bash restart.sh
# ===================================================================

set -u

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR_WIN="$(cygpath -w "$BACKEND_DIR" 2>/dev/null || echo "$BACKEND_DIR")"
PORT=8080

echo "=============================================================="
echo "  Spring Boot 后端一键重启"
echo "  DIR  = $BACKEND_DIR"
echo "  PORT = $PORT"
echo "=============================================================="
echo ""

# --- 步骤 1: 精准杀 learning-platform 的 Java 进程 ---
echo "[1/5] 杀掉残留 Java 进程（jps）..."
killed=0
while IFS= read -r pid; do
    if [ -n "$pid" ]; then
        echo "      killing pid=$pid"
        taskkill //F //PID "$pid" >/dev/null2>&1 || true
        killed=$((killed + 1))
    fi
done < <(jps -l 2>/dev/null | grep -iE "learning-platform|spring-boot" | awk '{print $1}')

if [ "$killed" -gt 0 ]; then
    echo "      [+] 已杀 $killed 个 Java 进程"
else
    echo "      [-] 没有残留 Java 进程"
fi

# --- 步骤 2: 兜底按端口杀 ---
echo "[2/5] 兜底杀掉占用 $PORT 端口的进程..."
port_killed=0
# 用 netstat + taskkill
while IFS= read -r pid; do
    if [ -n "$pid" ]; then
        echo "      killing pid=$pid"
        taskkill //F //PID "$pid" >/dev/null2>&1 || true
        port_killed=$((port_killed + 1))
    fi
done < <(netstat -aon 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)

if [ "$port_killed" -gt 0 ]; then
    echo "      [+] 已杀 $port_killed 个端口占用进程"
else
    echo "      [-] 端口 $PORT 未被占用"
fi

# --- 步骤 3: 等待端口释放 ---
echo "[3/5] 等待端口释放..."
waited=0
while true; do
    if ! netstat -aon 2>/dev/null | grep ":$PORT " | grep -q LISTENING; then
        echo "      [+] 端口 $PORT 已释放（等待 ${waited}秒）"
        break
    fi
    waited=$((waited + 1))
    if [ "$waited" -ge 10 ]; then
        echo "      [!] 端口 $PORT 10秒内未释放，请检查"
        exit 1
    fi
    sleep 1
done

# --- 步骤 4: 启动后端 ---
echo "[4/5] 启动 Spring Boot（新窗口: Java-Backend）..."
cmd.exe /c start "Java-Backend ($PORT)" cmd /k "cd /d \"$BACKEND_DIR_WIN\" && mvnw.cmd spring-boot:run"

echo "      [+] 启动命令已发送，等待就绪..."

# --- 步骤 5: 健康检查 ---
echo "[5/5] 健康检查（最多 90s）..."
waited=0
while true; do
    waited=$((waited + 5))
    if powershell -NoProfile -Command \
        "(Test-NetConnection -ComputerName 127.0.0.1 -Port $PORT -InformationLevel Quiet -WarningAction SilentlyContinue)" \
        >/dev/null2>&1; then
        echo ""
        echo "=============================================================="
        echo "  ✅ 后端已就绪 http://127.0.0.1:$PORT"
        echo "  SpringBoot 首次启动可能 30-60s，日志看 Java-Backend 窗口"
        echo "=============================================================="
        exit 0
    fi
    echo "      [t=${waited}s] :$PORT 等待中..."
    if [ "$waited" -ge 90 ]; then
        echo ""
        echo "=============================================================="
        echo "  ⚠️ 超时（90s）请到 Java-Backend 窗口看启动日志"
        echo "=============================================================="
        exit 1
    fi
    sleep 5
done