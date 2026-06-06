@echo off
REM Claude Loop 归档脚本（Windows 版本）
REM 用途：将当前轮次归档到 history/，准备开始新轮次

setlocal enabledelayedexpansion

cd /d "%~dp0.."

REM 检查 active 目录是否有文件
if not exist ".claude-loop\active\01-claude-plan.md" if not exist ".claude-loop\active\02-deepseek-code.md" (
    echo [警告] active 目录为空，无需归档
    exit /b 0
)

REM 生成归档目录名（时间戳）
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set ROUND_ID=%datetime:~0,8%-%datetime:~8,6%
set ARCHIVE_DIR=.claude-loop\history\round-%ROUND_ID%

REM 创建归档目录
if not exist "%ARCHIVE_DIR%" mkdir "%ARCHIVE_DIR%"

REM 移动文件
echo [信息] 正在归档当前轮次...
move /Y .claude-loop\active\* "%ARCHIVE_DIR%\" >nul 2>&1

REM 显示归档信息
echo [成功] 归档完成
echo 归档位置：%ARCHIVE_DIR%
echo.
echo 归档文件：
dir /b "%ARCHIVE_DIR%"
echo.
echo [成功] active 目录已清空，可以开始新轮次

endlocal
