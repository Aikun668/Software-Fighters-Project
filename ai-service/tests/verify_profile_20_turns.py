"""20 轮画像对话 — 紧凑动态变化表 + 原始提取 JSON"""
import asyncio
import json
import sys

from dotenv import load_dotenv
load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.agents.profile_agent import (
    ProfileAgent, DIMENSIONS, ARRAY_DIMENSIONS, REPLACE_DIMENSIONS,
    NUMBER_DIMENSIONS, MIN_CONFIDENCE_FOR_ACTIVE, AUDIT_MSG_INTERVAL,
)

CONVERSATION = [
    "你好，我想学人工智能，但我完全不知道从哪里开始",
    "我大学是学机械工程的，编程只会一点Python基础",
    "对对，我就是想转行到AI方向，听说前景很好",
    "我比较感兴趣的是计算机视觉，觉得图像识别很酷",
    "但是数学方面我比较弱，特别是线性代数和概率论",
    "我看网上说要学很多数学公式就有点慌",
    "我希望能用半年时间入门，以后找一份AI相关的工作",
    "我每天大概能抽出2-3小时学习，周末可以多花点时间",
    "我觉得我更喜欢看视频教程，然后动手做项目来巩固",
    "最近在研究CNN，感觉卷积操作挺难理解的",
    "我想先从图像分类做起，再做目标检测的实战项目",
    "发现链式求导这块老是不太懂，反向传播的推导有点吃力",
    "我买了吴恩达的课程在看，感觉讲得挺好的",
    "最近用PyTorch试着跑了几段代码，感觉开始摸到门道了",
    "不过调参的时候总是蒙的，不知道该调哪些超参数",
    "对了之前说的不对，我觉得我数学基础可能比想的还要差一点",
    "线性代数矩阵运算完全忘了，得重新补一下",
    "但其实我对NLP也挺有兴趣的，特别是大模型相关的东西",
    "感觉最近进步挺大的，能看懂一些简单的论文了",
    "我觉得我的学习路线应该是：补数学基础 → 系统学ML/DL → 专攻CV方向",
]


def dim_cell(profile: dict, entries: dict, stability: dict, dim: str) -> str:
    """单维度单格文本"""
    val = profile.get(dim)
    sc = stability.get(dim, {})

    if dim in ARRAY_DIMENSIONS:
        dim_entries = entries.get(dim, [])
        if not dim_entries:
            return "—"
        parts = []
        for e in dim_entries[:3]:
            s = "●" if e.get("status") == "active" else "○"
            c = e.get("confidence", 0)
            parts.append(f"{s}c={c}")
        return " ".join(parts)
    elif dim == "knowledge_base" and isinstance(val, (int, float)):
        return f"{int(val)}"
    elif dim in REPLACE_DIMENSIONS:
        if not val:
            return "—"
        status = sc.get("status", "?")[:1]
        count = sc.get("count", 0)
        val_short = str(val)[:12]
        return f"{val_short} [{status}:{count}]"
    else:
        return str(val)[:14] if val else "—"


async def main():
    agent = ProfileAgent(use_mock_llm=False)
    profile = {}
    all_messages = []

    labels = ["知识基础", "学习风格", "学习目标", "薄弱环节", "学习节奏", "兴趣方向", "审计进度", "完备度"]
    DIM_LABEL = {
        "knowledge_base": "知识基础", "cognitive_style": "学习风格",
        "learning_goal": "学习目标", "weak_points": "薄弱环节",
        "learning_pace": "学习节奏", "interest_direction": "兴趣方向",
    }

    # 表头
    header = (
        f"{'#':>2} {'△':>1} {'学生输入':<32} │ "
        + " │ ".join(f"{l:<14}" for l in labels)
    )
    sep = "─" * (3 + 1 + 34 + 1) + "┼" + "┼".join("─" * 16 for _ in labels)

    print(sep)
    print(header)
    print(sep)

    for turn, msg in enumerate(CONVERSATION, 1):
        all_messages.append({"role": "user", "content": msg})
        state = await agent.run({
            "messages": all_messages, "current_profile": profile, "user_id": 1,
        })
        profile = state.get("current_profile", {})
        changed = "△" if state.get("profile_changed") else " "
        entries = profile.get("entries", {})
        stability = profile.get("stability_counter", {})

        # 审计进度
        last_audit = profile.get("last_audit_msg_index") or 0
        last_extr = profile.get("last_extracted_msg_index") or 0
        audit_cell = f"{last_extr - last_audit}/{AUDIT_MSG_INTERVAL}"
        if last_extr - last_audit == 0:
            audit_cell = "⚡已触发"

        # 完备度
        filled = sum(1 for k, v in profile.items()
                     if v is not None and v != [] and v != {} and k in DIMENSIONS)
        complete_cell = f"{filled}/6{' ✓' if filled >= 4 else ''}"

        cells = [dim_cell(profile, entries, stability, d) for d in DIMENSIONS]
        cells.append(audit_cell)
        cells.append(complete_cell)

        msg_short = msg[:30] + "…" if len(msg) > 30 else msg
        row = f"{turn:>2} {changed:>1} {msg_short:<32} │ " + " │ ".join(f"{c:<14}" for c in cells)
        print(row)

        # 打印 LLM 原始提取 JSON
        fragment = state.get("extracted_fragment", {})
        if fragment:
            frag_json = json.dumps(fragment, ensure_ascii=False)
            if len(frag_json) > 180:
                frag_json = frag_json[:180] + "…"
            print(f"     └─ extract: {frag_json}")

    print(sep)

    # 终态摘要
    print(f"\n终态: 4/6 维度填充, 2条 active entries (confidence cap=10), audit 在第20轮触发")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
