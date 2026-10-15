"""T5 契约：SSE 事件契约必须与 T0 基线逐字段一致。

T5 红线：`sse_contract.json`（sha256 866a6c6d…）是冻结的对外 SSE 契约，
结构改造不得改变它。本测试跑 `probe_sse_contract.py --verify`（重新生成 +
精确 diff），不一致即失败并报出差异路径。

背景：T4-C 曾把 `final_status` 泄漏进 done 载荷的 results[]，正是本测试要防的。
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, ".."))
BASELINE_DIR = os.path.abspath(
    os.path.join(AI_SERVICE, "..", "docs", "agent-engineering", "routing-baseline")
)
PROBE = os.path.join(BASELINE_DIR, "probe_sse_contract.py")


@pytest.mark.skipif(not os.path.exists(PROBE), reason="SSE 契约探针不存在")
def test_sse_contract_matches_baseline():
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, PROBE, "--verify"],
        cwd=AI_SERVICE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=600,
    )
    # 探针故意制造的终态用例会往 stderr 打异常栈，只看退出码与 stdout
    assert proc.returncode == 0, (
        "SSE 契约偏离基线：\n" + (proc.stdout or "")[-3000:]
    )
