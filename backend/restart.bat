@echo off
REM ===================================================================
REM  Spring Boot 后端一键重启脚本（Windows / Agent 友好）
REM -------------------------------------------------------------------
REM  适用场景：
REM    - application.yml 改动后需要重启
REM    - Java 代码改动后需要重启
REM    - 8080 端口被老进程占用无法启动新进程
REM    - Ctrl+C 没杀干净 javaw.exe，任务管理器又懒得开
REM
REM  用法：
REM    1. 用户:   双击 restart.bat
REM    2. Agent:  cmd /c restart.bat
REM
REM  做的事：
REM    1. 精准杀掉 learning-platform 的 Java 进程（jps）
REM    2. 兜底杀掉占用 8080 端口的所有进程
REM    3. 等待端口释放
REM    4. 重新启动 spring-boot:run
REM    5. 健康检查（最多等 90s）
REM
REM  前置：MySQL + Redis 已运行（否则启动会失败）
REM ===================================================================

chcp65001 >nul
setlocal EnableDelayedExpansion

set "BACKEND_DIR=%~dp0"
set "PORT=8080"

echo.
echo ==============================================================
echo   Spring Boot 后端一键重启
echo   DIR  = %BACKEND_DIR%
echo   PORT = %PORT%
echo ==============================================================
echo.

REM --- 步骤 1: 精准杀 learning-platform 的 Java 进程 ---
echo [1/5] 杀掉残留 Java 进程（jps）...
set "killed=0"
for /f "tokens=1" %%p in ('jps -l 2^>nul ^| findstr /i "learning-platform\|spring-boot"') do (
    echo       killing pid=%%p
    taskkill /f /pid %%p >nul2>&1
    set /a killed+=1
)
if !killed! gtr 0 (
    echo       [+] 已杀 !killed! 个 Java 进程
) else (
    echo       [-] 没有残留 Java 进程
)

REM --- 步骤 2: 兜底按端口杀 ---
echo [2/5] 兜底杀掉占用 %PORT% 端口的进程...
set "port_killed=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo       killing pid=%%a
    taskkill /f /pid %%a >nul2>&1
    set /a port_killed+=1
)
if !port_killed! gtr 0 (
    echo       [+] 已杀 !port_killed! 个端口占用进程
) else (
    echo       [-] 端口 %PORT% 未被占用
)

REM --- 步骤 3: 等待端口释放 ---
echo [3/5] 等待端口释放...
set /a waited=0
:wait_port
set /a waited+=1
netstat -aon | findstr :%PORT% | findstr LISTENING >nul2>&1
if !errorlevel! neq 0 (
    echo       [+] 端口 %PORT% 已释放（等待 !waited! 秒）
    goto :port_free
)
if !waited! geq 10 (
    echo       [!] 端口 %PORT% 10 秒内未释放，请检查
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_port

:port_free

REM --- 步骤 4: 启动后端 ---
echo [4/5] 启动 Spring Boot（新窗口: Java-Backend）...
start "Java-Backend (%PORT%)" cmd /k "cd /d "%BACKEND_DIR%" && mvnw.cmd spring-boot:run"

echo       [+] 启动命令已发送，等待就绪...

REM --- 步骤 5: 健康检查 ---
echo [5/5] 健康检查（最多 90s）...
set /a waited=0
:health_loop
set /a waited+=5
powershell -NoProfile -Command ^
  "$c = Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -InformationLevel Quiet -WarningAction SilentlyContinue; ^
   if ($c) { Write-Host ('      [t=' + %waited% + 's] :%PORT% OK'); exit 0 } ^
   else { Write-Host ('      [t=' + %waited% + 's] :%PORT% 等待中...'); exit 1 }" >nul2>&1

if !errorlevel! equ 0 (
    echo.
    echo ==============================================================
    echo   ✅ 后端已就绪 http://127.0.0.1:%PORT%
    echo   SpringBoot 首次启动可能 30-60s，日志看 Java-Backend 窗口
    echo ==============================================================
    exit /b 0
)

if !waited! geq 90 (
    echo.
    echo ==============================================================
    echo   ⚠️ 超时（90s）请到 Java-Backend 窗口看启动日志
    echo ==============================================================
    exit /b 1
)

timeout /t 5 /nobreak >nul
goto :health_loop

endlocal