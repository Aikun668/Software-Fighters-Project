"""Stage 0.3 · Gold Label 草案生成器（人工语义判断，不参考旧路由预测）。

[只读输入] routing_cases.jsonl（140 条，Stage 0.2 交付，未改）
[产出] routing_gold_review.csv（UTF-8-BOM）

设计要点：
- 标准答案按「用户真实语义」判定，**不运行** ai-service 任何路由代码。
- 对 solve_problem / code_example / diagnose / profile_building 四意图，
  额外拆分三列：registered_intent（已注册意图）/ layer1_entry（一级入口）/
  independent_task（是否应作为独立执行任务），**不**直接归类为「产品能力缺失」。
- gold_status：DRAFT_CONFIRMED（无争议草案）/ POLICY_UNDECIDED（需产品裁决）。
- reviewer_decision 留空，待人工确认。

运行：
    python ../docs/agent-engineering/routing-baseline/build_routing_gold.py
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "routing_cases.jsonl")
OUT = os.path.join(HERE, "routing_gold_review.csv")

TQ = "tutor_question"
EX = "exercise_gen"
RE = "resource_gen"
LP = "learning_path"
FC = "flashcard_gen"
VZ = "visualize"
KG = "knowledge_graph"
CE = "code_example"
SP = "solve_problem"
DG = "diagnose"
PB = "profile_building"

# 四意图三拆分：已注册意图=是 / 一级入口=缺失 / 独立任务=待裁决
SPECIAL = {SP, CE, DG, PB}

DRAFT = "DRAFT_CONFIRMED"
UNDEC = "POLICY_UNDECIDED"

# 语义速记
R_CONCEPT = "概念/原理提问，无能力证据，属默认答疑。"
R_EXERCISE = "明确出题诉求，命中 EXERCISE。"
R_RESOURCE = "明确资源/讲义/资料诉求，命中 RESOURCE。"
R_PLAN = "学习规划诉求，命中 PLAN。"
R_VIS = "可视化诉求，命中 VISUALIZATION。"
R_KG = "知识图谱子意图，命中 VISUALIZATION。"
R_SOLVE = "求解已有题目；solve_problem 已注册，一级入口缺失，是否独立任务待裁决。"
R_CODE = "诉求为代码示例；code_example 已注册，一级入口缺失，是否独立任务待裁决。"
R_DIAG = "掌握度/薄弱点诊断；diagnose 已注册，一级入口缺失，是否独立任务待裁决。"
R_PROFILE = "自述基础/背景，属画像构建；profile_building 已注册，一级入口缺失，是否独立任务待裁决。"


# case_id -> (gold_capability, [intents 按执行顺序], ask_clarify, reason, status)
G = {}

# ---- C001-C015 普通概念答疑 ----
for i in range(1, 16):
    G[f"C{i:03d}"] = ("NORMAL_CHAT", [TQ], "否", R_CONCEPT, DRAFT)

# ---- C016-C025 解答已有题目 ----
for i in range(16, 26):
    G[f"C{i:03d}"] = ("待裁决", [SP], "否", R_SOLVE, UNDEC)
G["C023"] = ("待裁决", [TQ], "是",
             "核对选择题答案、且未提供题面（参数不足）；意图处于答疑/解题边界，需裁决。", UNDEC)
G["C025"] = ("待裁决", [SP], "是",
             "题面缺失（无上文/无图片），需先追问补全题目。", UNDEC)

# ---- C026-C040 明确生成练习题 ----
for i in range(26, 41):
    G[f"C{i:03d}"] = ("EXERCISE", [EX], "否", R_EXERCISE, DRAFT)

# ---- C041-C050 明确生成学习资源 ----
for i in range(41, 51):
    G[f"C{i:03d}"] = ("RESOURCE", [RE], "否", R_RESOURCE, DRAFT)
G["C045"] = ("RESOURCE", [FC], "否", "单词卡片=闪卡诉求，命中 flashcard_gen。", DRAFT)
G["C046"] = ("RESOURCE", [FC], "否", "记忆卡=闪卡诉求，命中 flashcard_gen。", DRAFT)
G["C047"] = ("RESOURCE", [CE], "否", R_CODE, UNDEC)

# ---- C051-C060 学习规划 ----
for i in range(51, 61):
    G[f"C{i:03d}"] = ("PLAN", [LP], "否", R_PLAN, DRAFT)

# ---- C061-C070 可视化 ----
for i in range(61, 71):
    G[f"C{i:03d}"] = ("VISUALIZATION", [VZ], "否", R_VIS, DRAFT)
G["C066"] = ("VISUALIZATION", [KG], "否", R_KG, DRAFT)
G["C067"] = ("VISUALIZATION", [KG], "否", "查看已有知识图谱，按 knowledge_graph 处理。", DRAFT)

# ---- C071-C080 诊断与画像相关 ----
G["C071"] = ("待裁决", [DG], "否", R_DIAG, UNDEC)
G["C072"] = ("待裁决", [DG], "否", R_DIAG, UNDEC)
G["C073"] = ("待裁决", [PB], "否", R_PROFILE, UNDEC)
G["C074"] = ("待裁决", [PB], "否", R_PROFILE, UNDEC)
G["C075"] = ("待裁决", [PB], "否", R_PROFILE, UNDEC)
G["C076"] = ("EXERCISE", [DG, EX], "否",
             "出题测水平=出题+诊断；diagnose 是否独立任务待裁决。", UNDEC)
G["C077"] = ("待裁决", [DG], "否", R_DIAG, UNDEC)
G["C078"] = ("待裁决", [PB], "否", R_PROFILE, UNDEC)
G["C079"] = ("待裁决", [PB], "否", R_PROFILE, UNDEC)
G["C080"] = ("待裁决", [DG], "否", R_DIAG, UNDEC)

# ---- C081-C095 隐式需求非标准表达 ----
G["C081"] = ("待澄清", [TQ, EX], "是", "「多来点」指代不明（讲解 or 练习），需追问。", UNDEC)
G["C082"] = ("待澄清", [TQ], "是", "情绪表达（有点晕），未明确请求，建议追问或默认讲解。", UNDEC)
G["C083"] = ("待澄清", [TQ, VZ], "是", "「记不住」可讲解/图示/闪卡，需追问。", UNDEC)
G["C084"] = ("EXERCISE", [EX], "否", "隐式出题表达（搞点题）；词表外延是否覆盖待裁决。", UNDEC)
G["C085"] = ("待澄清", [RE, EX, LP], "是", "「准备点东西」诉求不明，需追问。", UNDEC)
G["C086"] = ("待澄清", [TQ], "是", "纯情绪表达（好难啊），未表达诉求，需追问。", UNDEC)
G["C087"] = ("待澄清", [TQ, RE], "是", "「复习」可为讲解或资料，需追问或定默认。", UNDEC)
G["C088"] = ("NORMAL_CHAT", [TQ], "否", "明确请求再讲一遍，属答疑。", DRAFT)
G["C089"] = ("待澄清", [RE, LP], "是", "求「好办法」可为资源或计划，需追问。", UNDEC)
G["C090"] = ("待澄清", [RE, EX, LP], "是", "「明天要考」隐含需求不明，需追问。", UNDEC)
G["C091"] = ("NORMAL_CHAT", [TQ], "否", "明确请求展开讲解，属答疑。", DRAFT)
G["C092"] = ("待裁决", [DG], "否", R_DIAG, UNDEC)
G["C093"] = ("待澄清", [RE, EX], "是", "「找项目练手」可为资料或练习，需追问。", UNDEC)
G["C094"] = ("NORMAL_CHAT", [TQ], "否", "求讲解套路，属答疑。", DRAFT)
G["C095"] = ("待澄清", [TQ, PB], "是", "「一头雾水」可为讲解或画像，需追问。", UNDEC)

# ---- C096-C115 多轮上下文与指代 ----
G["C096"] = ("NORMAL_CHAT", [TQ], "否", "承接「二叉搜索树」追问，属答疑。", DRAFT)
G["C097"] = ("EXERCISE", [EX], "否", "「再来5道」承接口径=出题。", DRAFT)
G["C098"] = ("VISUALIZATION", [VZ], "否", "上文已生成流程图，要求更详细=重绘，上下文充足。", DRAFT)
G["C099"] = ("PLAN", [LP], "否", "修改既有计划时长，上下文充足。", DRAFT)
G["C100"] = ("RESOURCE", [RE], "否", "承接资料推荐，请求更多。", DRAFT)
G["C101"] = ("NORMAL_CHAT", [TQ], "否", "就上一轮题目追问解析，属答疑。", DRAFT)
G["C102"] = ("NORMAL_CHAT", [TQ], "否", "承接「进程」追问线程，属答疑。", DRAFT)
G["C103"] = ("RESOURCE", [CE], "否", "承接快排思路，请求代码实现（code_example）。" + R_CODE, UNDEC)
G["C104"] = ("EXERCISE", [EX], "否", "改题型，仍为出题。", DRAFT)
G["C105"] = ("VISUALIZATION", [KG], "否", "承接知识图谱，展开子节点。", DRAFT)
G["C106"] = ("PLAN", [LP], "否", "修改既有计划，增补内容。", DRAFT)
G["C107"] = ("待裁决", [DG], "否", "承接诊断结论追问补强方向。" + R_DIAG, UNDEC)
G["C108"] = ("NORMAL_CHAT", [TQ], "否", "请求举例说明，属答疑。", DRAFT)
G["C109"] = ("EXERCISE", [EX], "否", "调整既有题目难度，仍为出题。", DRAFT)
G["C110"] = ("VISUALIZATION", [VZ], "否", "追加画图。", DRAFT)
G["C111"] = ("待裁决", [PB], "否", "承接画像追问，确认转行=画像信息，上下文充足。" + R_PROFILE, UNDEC)
G["C112"] = ("EXERCISE", [EX], "否", "承接资料推荐，追加练习题。", DRAFT)
G["C113"] = ("NORMAL_CHAT", [TQ], "否", "承接上文，请求更通俗讲解，属答疑。", DRAFT)
G["C114"] = ("PLAN", [LP], "否", "调整既有学习路径顺序。", DRAFT)
G["C115"] = ("VISUALIZATION", [VZ], "否", "把前文内容整理成图。", DRAFT)

# ---- C116-C130 复合任务（多中心编排策略待裁决）----
_COMPOUND = {
    "C116": ("EXERCISE", [TQ, EX], "讲解 B+树 + 出题，含两个诉求，需多中心编排。"),
    "C117": ("EXERCISE", [TQ, EX], "讲解快排 + 练习，含两个诉求。"),
    "C118": ("EXERCISE", [TQ, EX], "讲解死锁 + 出题，含两个诉求。"),
    "C119": ("PLAN", [LP, VZ], "计划 + 流程图，跨中心（PLAN+VISUALIZATION）。"),
    "C120": ("RESOURCE", [RE, EX], "讲义 + 练习，跨中心（RESOURCE+EXERCISE）。"),
    "C121": ("VISUALIZATION", [TQ, VZ], "讲解 + 配图，跨中心。"),
    "C122": ("PLAN", [DG, PB, LP], "诊断 + 画像 + 计划，三中心链；含 diagnose/profile 待裁决。"),
    "C123": ("EXERCISE", [SP, EX], "解题 + 找类似题；{solve_problem, exercise_gen} 互斥需裁决。"),
    "C124": ("VISUALIZATION", [VZ, EX], "思维导图 + 出题，跨中心。"),
    "C125": ("VISUALIZATION", [TQ, VZ], "讲解 + 图示，跨中心。"),
    "C126": ("PLAN", [LP, RE], "学习路线 + 资料，跨中心（PLAN+RESOURCE）。"),
    "C127": ("EXERCISE", [EX, KG], "出题 + 知识图谱，跨中心（EXERCISE+VISUALIZATION）。"),
    "C128": ("RESOURCE", [TQ, CE], "讲解 + 代码示例，跨中心；含 code_example 待裁决。"),
    "C129": ("EXERCISE", [DG, EX], "诊断 + 针对性练习；含 diagnose 待裁决。"),
    "C130": ("PLAN", [RE, LP], "资料 + 计划，跨中心（RESOURCE+PLAN）。"),
}
for cid, (cap, intents, note) in _COMPOUND.items():
    G[cid] = (cap, intents, "是", "复合任务：" + note, UNDEC)

# ---- C131-C135 否定表达引用内容干扰 ----
G["C131"] = ("NORMAL_CHAT", [TQ], "否", "明确否定出题，只要讲解，属答疑。", DRAFT)
G["C132"] = ("NORMAL_CHAT", [TQ], "否", "明确否定画图，要文字说明，属答疑。", DRAFT)
G["C133"] = ("待裁决", [SP], "否", "否定「怎么出题」，真实诉求=解这道题；含 solve_problem 待裁决。", UNDEC)
G["C134"] = ("NORMAL_CHAT", [TQ], "否", "否定资源推荐，要求讲清概念，属答疑。", DRAFT)
G["C135"] = ("待澄清", [TQ], "是", "转述/引用「出题」，未表达明确请求，需追问。", UNDEC)

# ---- C136-C140 空输入模糊请求缺少参数 ----
for cid in ("C136", "C137", "C138", "C139", "C140"):
    G[cid] = ("待澄清", [], "是", "空/过短/无信息输入，未表达可路由诉求，需追问引导。", UNDEC)


def special_cols(intents):
    """四意图三拆分列；命中任一特殊意图即填充，否则为 —。"""
    if any(i in SPECIAL for i in intents):
        return "是", "缺失", "待裁决"
    return "—", "—", "—"


def task_order(intents):
    if len(intents) <= 1:
        return ""
    return ">".join(f"{i}({n})" for n, i in enumerate(intents, 1))


COLUMNS = [
    "case_id", "category", "message", "mode",
    "gold_capability", "gold_intents", "gold_task_order", "gold_ask_clarify", "gold_reason",
    "registered_intent", "layer1_entry", "independent_task",
    "gold_status", "reviewer_decision",
]


def main() -> None:
    rows = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            cid = o["case_id"]
            if cid not in G:
                raise KeyError(f"缺 Gold 草案：{cid}")
            cap, intents, ask, reason, status = G[cid]
            reg, l1, indep = special_cols(intents)
            rows.append({
                "case_id": cid,
                "category": o["category"],
                "message": o["message"],
                "mode": o["mode"],
                "gold_capability": cap,
                "gold_intents": "|".join(intents),
                "gold_task_order": task_order(intents),
                "gold_ask_clarify": ask,
                "gold_reason": reason,
                "registered_intent": reg,
                "layer1_entry": l1,
                "independent_task": indep,
                "gold_status": status,
                "reviewer_decision": "",
            })

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    undec = [r["case_id"] for r in rows if r["gold_status"] == UNDEC]
    print(f"rows={len(rows)} -> {OUT}")
    print(f"DRAFT_CONFIRMED={len(rows) - len(undec)}  POLICY_UNDECIDED={len(undec)}")
    print("POLICY_UNDECIDED:", ",".join(undec))


if __name__ == "__main__":
    main()
