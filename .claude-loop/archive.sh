#!/bin/bash
# Claude Loop 归档脚本
# 用途：将当前轮次归档到 history/，准备开始新轮次

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 检查 active 目录是否有文件
if [ ! -f ".claude-loop/active/01-claude-plan.md" ] && [ ! -f ".claude-loop/active/02-deepseek-code.md" ]; then
    echo -e "${YELLOW}警告：active 目录为空，无需归档${NC}"
    exit 0
fi

# 生成归档目录名（时间戳）
ROUND_ID=$(date +%Y%m%d-%H%M%S)
ARCHIVE_DIR=".claude-loop/history/round-$ROUND_ID"

# 创建归档目录
mkdir -p "$ARCHIVE_DIR"

# 移动文件
echo -e "${GREEN}正在归档当前轮次...${NC}"
mv .claude-loop/active/* "$ARCHIVE_DIR/" 2>/dev/null || true

# 显示归档信息
echo -e "${GREEN}✓ 归档完成${NC}"
echo "归档位置：$ARCHIVE_DIR"
echo ""
echo "归档文件："
ls -lh "$ARCHIVE_DIR/"
echo ""
echo -e "${GREEN}active 目录已清空，可以开始新轮次${NC}"
