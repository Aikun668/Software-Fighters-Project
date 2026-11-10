@echo off
REM ===================================================================
REM  Software-Fighters-Project 一键启动脚本（Windows / Agent 友好）
REM -------------------------------------------------------------------
REM  用法：
REM    1. 用户:   双击 start-all.bat
REM    2. Agent:  bash start-all.sh   或   cmd /c start-all.bat
REM
REM  端口约定：
REM    Python AI 服务  -> 8001
REM    Java 后端       -> 8080
REM    前端 dev server -> 5173
REM
REM  前置依赖（agent 跑前应已就绪）：
REM    - MySQL 8.0 已运行且库表已初始化（sql/ 目录）
REM    - Redis 7 已运行
REM    - ai-service/.env 已填写 LLM API Key
REM    - ai-service/venv 已存在（或系统 Python 装好了依赖）
REM    - frontend/node_modules 已安装
REM ===================================================================

chcp 65001 >nul
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "AI_DIR=%ROOT%ai-service"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"

echo.
echo ==============================================================
echo   Software-Fighters-Project 一键启动
echo   ROOT = %ROOT%
echo ==============================================================
echo.

REM --- 步骤 1: 启动 3 个服务到独立窗口 ---
echo [1/4] 启动 Python AI 服务 (窗口: AI-Service) ...
start "AI-Service (8001)" cmd /k "cd /d "%AI_DIR%" && python main.py"

echo [2/4] 启动 Java 后端     (窗口: Java-Backend) ...
start "Java-Backend (8080)" cmd /k "cd /d "%BACKEND_DIR%" && mvnw.cmd spring-boot:run"

echo [3/4] 启动前端 dev server (窗口: Frontend) ...
start "Frontend (5173)" cmd /k "cd /d "%FRONTEND_DIR%" && pnpm dev"

echo.
echo [4/4] 等待服务就绪（最多 90s）...

REM --- 步骤 2: 健康检查（端口探测）---
set /a waited=0
:health_loop
set /a waited+=5
echo     [t=!waited!s] 探测 8001 / 8080 / 5173 ...

REM 用 powershell 探测端口（比 netstat 兼容性好）
powershell -NoProfile -Command ^
  "$ports = @(8001,8080,5173); ^
   $open = 0; ^
   foreach ($p in $ports) { ^
     $c = Test-NetConnection -ComputerName 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue; ^
     if ($c) { Write-Host ('      [+] :' + $p + ' OK'); $open++ } ^
     else { Write-Host ('      [-] :' + $p + ' 等待中...') } ^
   }; ^
   if ($open -eq 3) { exit 0 } else { exit 1 }" >nul 2>&1

if !errorlevel! equ 0 (
    echo.
    echo ==============================================================
    echo   ✅ 3 个服务均已就绪
    echo     - AI  Service:  http://127.0.0.1:8001
    echo     - Java Backend: http://127.0.0.1:8080
    echo     - Frontend:    http://127.0.0.1:5173
    echo ==============================================================
    exit /b 0
)

if !waited! geq 90 (
    echo.
    echo ==============================================================
    echo   ⚠️ 超时（90s）部分服务未就绪
    echo     请到对应窗口查看启动日志（SpringBoot 首次启动需 30-60s）
    echo ==============================================================
    exit /b 1
)

timeout /t 5 /nobreak >nul
goto :health_loop

endlocal