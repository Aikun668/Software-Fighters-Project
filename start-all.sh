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
#    - showcase-web/node_modules 已安装
# ===================================================================

set -u

# Windows 路径转 POSIX（脚本可能从 cmd 调过来）
ROOT="$(cd "$(dirname "$0")" && pwd)"
ROOT_WIN="$(cygpath -w "$ROOT" 2>/dev/null || echo "$ROOT")"

AI_DIR="$ROOT/ai-service"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/showcase-web"

# cmd 的 cd /d 只认 Windows 形式路径（D:\...）。
# 注意：不能用 ${AI_DIR//\//\\}，那会把 /d/My_... 变成 \d\My_...（丢掉盘符冒号），
# cmd 找不到该路径会静默失败，导致 python/main.py 根本不执行。
AI_DIR_WIN="$(cygpath -w "$AI_DIR" 2>/dev/null || echo "$AI_DIR")"
BACKEND_DIR_WIN="$(cygpath -w "$BACKEND_DIR" 2>/dev/null || echo "$BACKEND_DIR")"
FRONTEND_DIR_WIN="$(cygpath -w "$FRONTEND_DIR" 2>/dev/null || echo "$FRONTEND_DIR")"

# --- JDK 选择 ---
# pom.xml 是 java.version=17，但本机 JAVA_HOME 指向 JDK 25，
# 而 lombok 1.18.38 在 JDK 25 下注解处理会失效，
# 表现为满屏 "找不到符号: getId() / getUserId() / log" 然后 BUILD FAILURE。
# 因此必须显式指向一个 JDK 17 再跑 mvnw。找不到就沿用默认并给出警告。
JAVA17_HOME=""
for cand in \
    "/c/Program Files/ojdkbuild/java-17-openjdk-17.0.3.0.6-1" \
    "/c/Program Files/Eclipse Adoptium"/jdk-17* \
    "/c/Program Files/Java"/jdk-17* \
    "/c/Program Files/Microsoft"/jdk-17*
do
    if [ -x "$cand/bin/java.exe" ]; then
        JAVA17_HOME="$cand"
        break
    fi
done

if [ -n "$JAVA17_HOME" ]; then
    JAVA17_HOME_WIN="$(cygpath -w "$JAVA17_HOME" 2>/dev/null || echo "$JAVA17_HOME")"
    echo "[env] 使用 JDK 17: $JAVA17_HOME_WIN"
else
    JAVA17_HOME_WIN=""
    echo "[env] [!] 未找到 JDK 17，将使用默认 JDK；若后端编译报 lombok 相关"
    echo "         '找不到符号' 错误，请安装 JDK 17 或改 pom 的 java.version。"
fi
echo ""

echo "=============================================================="
echo "  Software-Fighters-Project 一键启动"
echo "  ROOT = $ROOT"
echo "=============================================================="
echo ""

# --- 步骤 1: 启动 3 个服务到独立窗口 ---
# 为什么先生成 .bat 再去跑，而不是直接写：
#     cmd.exe /c start "..." cmd /k "cd /d \"...\" && python main.py"
# 因为 Git Bash(MSYS) 会把参数里的 /c 当成路径改写成 C:/，
# 还会破坏 start 的嵌套引号，结果是 cmd 只是"开了个交互式窗口什么都不干"，
# 但退出码依然是 0 —— 看起来像启动成功，实际一个服务都没起。
# 把命令写进 .bat 文件后，引号由 cmd 自己解析，不再经过 MSYS，稳定可靠。
#
# 另外 start 的窗口标题既是标题也是"要运行的程序"（标题必须带引号），
# 这里统一用 `start "标题" /D "目录" cmd /k 命令`，用 /D 指定工作目录，
# 避免再嵌套一层 cd 的引号。
LAUNCHER_DIR="$ROOT/.launch"
mkdir -p "$LAUNCHER_DIR"

# write_launcher <文件名> <窗口标题> <工作目录(Windows形式)> <命令> [预置环境变量行]
# 预置环境变量必须写成 .bat 里的独立一行（set "VAR=value"），
# 不能拼进 `cmd /k "set VAR=... && 命令"`：
#   1) 路径含空格时那样的引号会被 start 提前截断；
#   2) `set VAR=值 && ...` 会把值尾部的空格也存进去，
#      导致 %JAVA_HOME%\bin\java.exe 变成 "…\jdk-17 \bin\java.exe"（多一个空格）而找不到。
write_launcher() {
    local file="$1"
    local title="$2"
    local workdir="$3"
    local cmdline="$4"
    local preline="${5:-}"
    # 必须用 CRLF，且不写 BOM，否则 cmd 会报错或出现乱码
    {
        printf '@echo off\r\n'
        printf 'chcp 65001 >nul\r\n'
        if [ -n "$preline" ]; then
            printf '%s\r\n' "$preline"
        fi
        printf 'start "%s" /D "%s" cmd /k %s\r\n' "$title" "$workdir" "$cmdline"
    } > "$LAUNCHER_DIR/$file"
    # 转成 Windows 路径后用 cmd 执行（stdio 重定向，避免 bash 等待窗口退出）
    cmd.exe //c "$(cygpath -w "$LAUNCHER_DIR/$file")" </dev/null >/dev/null 2>&1
}

echo "[1/4] 启动 Python AI 服务 (窗口: AI-Service) ..."
write_launcher "ai.bat" "AI-Service (8001)" "$AI_DIR_WIN" "python main.py"

echo "[2/4] 启动 Java 后端      (窗口: Java-Backend) ..."
if [ -n "$JAVA17_HOME_WIN" ]; then
    # 在 .bat 里先设 JAVA_HOME（新窗口会继承），避免用到默认的 JDK 25
    write_launcher "backend.bat" "Java-Backend (8080)" "$BACKEND_DIR_WIN" \
        "mvnw.cmd spring-boot:run" "set \"JAVA_HOME=$JAVA17_HOME_WIN\""
else
    write_launcher "backend.bat" "Java-Backend (8080)" "$BACKEND_DIR_WIN" \
        "mvnw.cmd spring-boot:run"
fi

echo "[3/4] 启动前端 dev server  (窗口: Frontend) ..."
write_launcher "showcase-web.bat" "Frontend (5173)" "$FRONTEND_DIR_WIN" "pnpm dev"

echo ""
echo "[4/4] 等待服务就绪（最多 90s）..."

# --- 步骤 2: 健康检查（端口探测）---
# 坑 1：不能用 `powershell -Command "(Test-NetConnection ...)"` 当条件。
#       端口关闭时它只是往 stdout 打印 "False"，进程退出码仍是 0，
#       于是 `if` 永远成立 —— 服务一个都没起来也会报"全部就绪"。
# 坑 2：`>/dev/null2>&1` 是笔误（少了空格），会生成一个名为 "null2" 的文件。
# 这里改用 curl：连不上时退出码非 0，且 HTTP 404 也算"端口已监听"。
# 坑 3：Vite 默认可能只监听 IPv6（::1），此时 127.0.0.1 连不上但 localhost 可以，
#       所以两个地址都要试。
probe_port() {
    local port=$1
    # 127.0.0.1 优先，回退到 localhost（覆盖 Vite 仅监听 IPv6 的情况）
    curl -s -o /dev/null --max-time 3 "http://127.0.0.1:$port/" 2>/dev/null && return 0
    curl -s -o /dev/null --max-time 3 "http://localhost:$port/" 2>/dev/null && return 0
    return 1
}

wait_for_port() {
    local port=$1
    local name=$2
    local waited=0
    local max=90
    while [ "$waited" -lt "$max" ]; do
        if probe_port "$port"; then
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