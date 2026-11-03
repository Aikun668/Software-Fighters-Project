#!/usr/bin/env python3
"""Haiku Relay v1. Stdlib-only helper, not an API token-limit enforcement tool."""
import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "relay"
TASKS = BASE / "tasks"
REPORTS = BASE / "reports"
VALID_ID = re.compile(r"^T[0-9]{3,5}$")


def run_git(*args):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return (p.stdout or p.stderr).strip() if p.returncode == 0 else "(不可用或非 Git 项目)"


def new_task(task_id, title):
    if not VALID_ID.fullmatch(task_id):
        raise ValueError("任务编号格式必须为 T001 或 T00001")
    TASKS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = TASKS / f"{task_id}.md"
    if path.exists():
        raise FileExistsError(f"任务已存在，不覆盖: {path}")
    txt = (BASE / "templates" / "TASK.md").read_text(encoding="utf-8")
    path.write_text(txt.replace("{{ID}}", task_id).replace("{{TITLE}}", title), encoding="utf-8")
    print(f"已创建 {path.relative_to(ROOT)}；请由总督填写全部验收/范围后再派发。")


def task_state(path):
    content = path.read_text(encoding="utf-8")
    m = re.search(r"^[-*] 状态:\s*(\S+)", content, re.MULTILINE)
    return m.group(1) if m else "missing"


def list_tasks():
    print("RELAY TASKS")
    if not list(TASKS.glob("T*.md")):
        print("  (none)")
    for path in sorted(TASKS.glob("T*.md")):
        report = "report" if (REPORTS / path.name).exists() else "no report"
        print(f"  {path.stem:<8} {task_state(path):<9} {report}")
    print("Git branch:", run_git("branch", "--show-current"))
    print("Git last:  ", run_git("log", "-1", "--oneline"))
    print("Git status:\n", run_git("status", "--short") or "(clean)")


def check():
    expected = [
        BASE / "README.md", BASE / "PROTOCOL.md", BASE / "state" / "PROJECT.md",
        BASE / "state" / "QUEUE.md", BASE / "state" / "DECISIONS.md",
        BASE / "state" / "GOVERNOR_WILL.md",
        ROOT / ".claude" / "skills" / "g-governor" / "SKILL.md",
        ROOT / ".claude" / "skills" / "g-worker" / "SKILL.md",
        ROOT / ".claude" / "skills" / "g-retire" / "SKILL.md",
    ]
    missing = [p.relative_to(ROOT) for p in expected if not p.is_file()]
    if missing:
        print("缺失文件:", *missing, sep="\n - ")
        return 1
    print("Relay 文件完备。Claude CLI:", shutil.which("claude") or "未找到（需安装或检查 PATH）")
    print("Git:", run_git("branch", "--show-current"))
    return 0


def launch(kind, arg=""):
    if not shutil.which("claude"):
        raise RuntimeError("无法找到 claude 命令，请先安装 Claude Code")
    if kind == "worker":
        if not VALID_ID.fullmatch(arg) or not (TASKS / f"{arg}.md").exists():
            raise ValueError("未找到合法任务。先由总督建立 relay/tasks/Txxx.md")
        prompt = f"请严格按 .claude/skills/g-worker/SKILL.md 执行 Worker 流程。任务 ID 是 {arg}。先读取 relay/tasks/{arg}.md；若任务单缺验收/范围则直接阻塞报告。"
    elif kind == "governor":
        prompt = "请严格按 .claude/skills/g-governor/SKILL.md 执行总督职责。用户目标：" + (arg or "继任，先检查项目状态并准备派包")
    else:
        raise ValueError("未知角色")
    print(f"启动 Claude Code / {kind}；项目目录: {ROOT}", flush=True)
    return subprocess.call(["claude", "--model", "haiku", prompt], cwd=ROOT)


def main():
    p = argparse.ArgumentParser(description="Haiku Relay｜任务管理与 Claude Code 会话启动")
    s = p.add_subparsers(dest="command", required=True)
    n = s.add_parser("new", help="创建任务包")
    n.add_argument("task_id"); n.add_argument("title")
    s.add_parser("status", help="列出任务与 Git 状态")
    s.add_parser("check", help="检查文件是否齐全")
    g = s.add_parser("governor", help="启动总督窗口")
    g.add_argument("goal", nargs="?", default="")
    w = s.add_parser("worker", help="启动临时 Worker 窗口")
    w.add_argument("task_id")
    args = p.parse_args()
    try:
        if args.command == "new": new_task(args.task_id, args.title)
        elif args.command == "status": list_tasks()
        elif args.command == "check": return check()
        elif args.command == "governor": return launch("governor", args.goal)
        elif args.command == "worker": return launch("worker", args.task_id)
    except (FileExistsError, ValueError, RuntimeError) as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
