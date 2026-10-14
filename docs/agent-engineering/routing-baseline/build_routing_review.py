"""Stage 0.2 · 任务 C/D 生成器：由 routing_cases.jsonl 产出评审用 CSV。

[只读输入] routing_cases.jsonl（人工构造，未被旧路由预测污染）
[产出] routing_cases_review.csv（UTF-8-BOM，供人工评审）

重要约束（Task B 原话）：
    「测试集必须独立于旧系统的实际预测结果设计。不要先运行旧路由，
      再根据它的输出反过来设计所谓的标准测试题。」
故本脚本**不导入、不运行** ai-service 的任何路由代码；suggested_* 全部来自
对「学生真实诉求」的人工判断，属**初步建议**，label_status 仍为「待人工审核」，
**不是**人工确认的 Gold Label。reviewer_decision 一律留空待人工裁决。

运行：
    python ../docs/agent-engineering/routing-baseline/build_routing_review.py
（在任意目录均可，脚本按自身位置定位 jsonl。）
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "routing_cases.jsonl")
OUT = os.path.join(HERE, "routing_cases_review.csv")

# ---------------------------------------------------------------------------
# 每案的人工「初步建议」。键=case_id；值=(suggested_capability, [intents],
# task_order, confirmation, reason, policy_question)。
# capability 取 CapabilityKind 名；多中心用 "+" 连接；需澄清用 待澄清。
# task_order 用 "intent(序号)>intent(序号)" 表达执行顺序；单任务留空。
# confirmation 为该案「是否应先向用户确认」的建议（是/否）。
# policy_question 区分「产品能力缺口」/「路由算法判断」/「产品决策(澄清策略)」。
# ---------------------------------------------------------------------------

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

# 语义速记
_R_CONCEPT = "概念/原理类提问，无能力证据，应走默认答疑路径（一级 gate→NORMAL_CHAT）。"
_R_SOLVE = "用户诉求是求解已有题目而非答疑；solve_problem 中心=auto 且一级无专属规则。"
_R_EXERCISE = "明确的出题诉求，应命中 EXERCISE 能力（关键词/数量词/题型产物齐备）。"
_R_RESOURCE = "明确的资源/讲义/资料诉求，应命中 RESOURCE 能力。"
_R_PLAN = "学习规划诉求，应命中 PLAN 能力。"
_R_VIS = "可视化/图示诉求，应命中 VISUALIZATION 能力。"
_R_IMPLICIT = "隐式需求，字面不含明确能力词；真实诉求需语义推断，可能需澄清。"
_R_MULTITURN = "多轮指代，须结合 history 才能确定诉求。"
_R_COMPOUND = "复合任务，含两个及以上诉求，需按顺序编排多中心。"
_R_NEGATION = "否定/引用表达，字面关键词与实际诉求方向相反或被引号包裹。"
_R_EMPTY = "空/过短/无信息输入，未表达任何可路由诉求。"


def P(kind: str, text: str) -> str:
    return f"{kind}：{text}"


# 产品能力缺口说明（复用不同措辞）
_GAP_SOLVE = P("产品能力缺口", "solve_problem 无一级能力入口，干净表达会被判 NORMAL_CHAT 落到答疑。")
_GAP_CODE = P("产品能力缺口", "code_example 无一级专属规则，需搭 RESOURCE 产物词的车才进二级。")
_GAP_DIAG = P("产品能力缺口", "diagnose 无一级能力入口，需靠 EXERCISE 复合句才进二级。")
_GAP_PROFILE = P("产品能力缺口", "profile_building 无一级能力入口，画像型自然表达基本落在答疑。")

SUGGEST = {
    # ---- C001-C015 普通概念答疑 ----
    **{f"C{i:03d}": ("NORMAL_CHAT", [TQ], "", "否", _R_CONCEPT, "") for i in range(1, 16)},

    # ---- C016-C025 解答已有题目 ----
    **{f"C{i:03d}": ("NORMAL_CHAT", [SP], "", "否", _R_SOLVE, _GAP_SOLVE) for i in range(16, 26)},
    "C023": ("NORMAL_CHAT", [TQ], "", "否", "核对选择题答案是否正确，属答疑而非求解。", ""),

    # ---- C026-C040 明确生成练习题 ----
    **{f"C{i:03d}": ("EXERCISE", [EX], "", "否", _R_EXERCISE, "") for i in range(26, 41)},

    # ---- C041-C050 明确生成学习资源 ----
    **{f"C{i:03d}": ("RESOURCE", [RE], "", "否", _R_RESOURCE, "") for i in range(41, 51)},
    "C045": ("RESOURCE", [FC], "", "否", "单词卡片=闪卡诉求，应命中 flashcard_gen。", ""),
    "C046": ("RESOURCE", [FC], "", "否", "记忆卡=闪卡诉求，应命中 flashcard_gen。", ""),
    "C047": ("RESOURCE", [CE], "", "否", "诉求是代码示例（code_example），非普通资源。", _GAP_CODE),

    # ---- C051-C060 学习规划 ----
    **{f"C{i:03d}": ("PLAN", [LP], "", "否", _R_PLAN, "") for i in range(51, 61)},

    # ---- C061-C070 可视化 ----
    **{f"C{i:03d}": ("VISUALIZATION", [VZ], "", "否", _R_VIS, "") for i in range(61, 71)},
    "C066": ("VISUALIZATION", [KG], "", "否", "知识图谱子意图（knowledge_graph），非普通图。", ""),
    "C067": ("VISUALIZATION", [KG], "", "否", "查看已有知识图谱，应按 knowledge_graph 处理。", ""),

    # ---- C071-C080 诊断与画像相关 ----
    "C071": ("NORMAL_CHAT", [DG], "", "否", "诊断薄弱点诉求。", _GAP_DIAG),
    "C072": ("NORMAL_CHAT", [DG], "", "否", "掌握度测试=诊断诉求。", _GAP_DIAG),
    "C073": ("NORMAL_CHAT", [PB], "", "否", "自我介绍基础=画像构建诉求。", _GAP_PROFILE),
    "C074": ("NORMAL_CHAT", [PB], "", "否", "自述基础差=画像构建诉求。", _GAP_PROFILE),
    "C075": ("NORMAL_CHAT", [PB], "", "否", "自述迷茫=画像构建诉求。", _GAP_PROFILE),
    "C076": ("EXERCISE", [DG, EX], f"{DG}(1)>{EX}(2)", "否", "出题测水平=诊断+出题复合。", _GAP_DIAG),
    "C077": ("NORMAL_CHAT", [DG], "", "否", "学习诊断诉求。", _GAP_DIAG),
    "C078": ("NORMAL_CHAT", [PB], "", "否", "自述年级与目标=画像构建诉求。", _GAP_PROFILE),
    "C079": ("NORMAL_CHAT", [PB], "", "否", "自述基础薄弱+能否学=画像构建诉求。", _GAP_PROFILE),
    "C080": ("NORMAL_CHAT", [DG], "", "否", "掌握度测试=诊断诉求。", _GAP_DIAG),

    # ---- C081-C095 隐式需求非标准表达 ----
    "C081": ("待澄清", [TQ, EX], f"{TQ}(1)?{EX}(2)", "是", _R_IMPLICIT + "「多来点」指代不明（讲解 or 练习）。", P("产品决策", "指代不明应澄清：是继续讲解还是补练习？")),
    "C082": ("NORMAL_CHAT", [TQ], "", "否", _R_IMPLICIT + "「有点晕」倾向请求再讲解。", ""),
    "C083": ("NORMAL_CHAT", [TQ, VZ], f"{VZ}(1)>{TQ}(2)", "是", _R_IMPLICIT + "「记不住」可解释为再讲或图示记忆。", P("产品决策", "「记不住」应补讲解、图示还是闪卡？缺默认策略。")),
    "C084": ("EXERCISE", [EX], "", "否", _R_IMPLICIT + "「搞点题练练」=出题意图，但无标准出题词。", P("路由算法", "隐式出题表达（搞点题）是否应被 EXERCISE 捕获？")),
    "C085": ("待澄清", [RE, EX, LP], "", "是", _R_IMPLICIT + "「准备点东西」诉求完全不明。", P("产品决策", "期末模糊请求应澄清意图（资料/练习/计划）。")),
    "C086": ("待澄清", [TQ], "", "是", _R_IMPLICIT + "「好难啊」为情绪表达，未表达具体诉求。", P("产品决策", "纯情绪表达应如何回应（安抚+追问 or 默认答疑）。")),
    "C087": ("NORMAL_CHAT", [TQ, RE], f"{TQ}(1)?{RE}(2)", "是", _R_IMPLICIT + "「复习」可为讲解或资料。", P("产品决策", "「复习」默认落到讲解还是资源？")),
    "C088": ("NORMAL_CHAT", [TQ], "", "否", "明确请求再讲一遍，属答疑。", ""),
    "C089": ("待澄清", [RE, LP], "", "是", "求学习英语口语的方法，可为资源或路径。", P("产品决策", "「有没有好办法」应给资源还是计划？")),
    "C090": ("待澄清", [RE, EX, LP], "", "是", "「明天要考」隐含复习/突击需求，未明确。", P("产品决策", "临考表达应澄清（要资料/练习/计划）。")),
    "C091": ("NORMAL_CHAT", [TQ], "", "否", "请求展开讲解，属答疑。", ""),
    "C092": ("NORMAL_CHAT", [DG], "", "否", "查漏=诊断诉求。", _GAP_DIAG),
    "C093": ("RESOURCE", [RE, EX], f"{RE}(1)?{EX}(2)", "是", "「找点项目练练手」可为资源或练习。", P("产品决策", "「项目练手」应给项目资料还是练习任务？")),
    "C094": ("NORMAL_CHAT", [TQ], "", "否", "求讲解套路/方法，属答疑。", ""),
    "C095": ("NORMAL_CHAT", [TQ, PB], f"{TQ}(1)?{PB}(2)", "是", "自述学习受挫，可为答疑或画像。", P("产品决策", "「一头雾水」默认讲解还是纳入画像？")),

    # ---- C096-C115 多轮上下文与指代 ----
    "C096": ("NORMAL_CHAT", [TQ], "", "否", _R_MULTITURN + "承接「二叉搜索树」追问。", ""),
    "C097": ("EXERCISE", [EX], "", "否", _R_MULTITURN + "「再来5道」承接口径=出题。", ""),
    "C098": ("VISUALIZATION", [VZ], "", "否", _R_MULTITURN + "承接画图，要求更详细。", ""),
    "C099": ("PLAN", [LP], "", "否", _R_MULTITURN + "修改既有计划时长。", ""),
    "C100": ("RESOURCE", [RE], "", "否", _R_MULTITURN + "承接资料推荐，请求更多。", ""),
    "C101": ("NORMAL_CHAT", [TQ], "", "否", _R_MULTITURN + "就上一轮题目追问解析。", ""),
    "C102": ("NORMAL_CHAT", [TQ], "", "否", _R_MULTITURN + "承接「进程」追问线程。", ""),
    "C103": ("RESOURCE", [CE], "", "否", _R_MULTITURN + "承接快排思路，请求代码实现（code_example）。", _GAP_CODE),
    "C104": ("EXERCISE", [EX], "", "否", _R_MULTITURN + "改题型，仍为出题。", ""),
    "C105": ("VISUALIZATION", [KG], "", "否", _R_MULTITURN + "承接知识图谱，展开子节点。", ""),
    "C106": ("PLAN", [LP], "", "否", _R_MULTITURN + "修改既有计划，增补内容。", ""),
    "C107": ("NORMAL_CHAT", [DG], "", "否", _R_MULTITURN + "承接诊断结论追问补强方向。", _GAP_DIAG),
    "C108": ("NORMAL_CHAT", [TQ], "", "否", _R_MULTITURN + "请求举例说明。", ""),
    "C109": ("EXERCISE", [EX], "", "否", _R_MULTITURN + "调整既有题目难度。", ""),
    "C110": ("VISUALIZATION", [VZ], "", "否", _R_MULTITURN + "追加画图。", ""),
    "C111": ("NORMAL_CHAT", [PB], "", "否", _R_MULTITURN + "确认转行=画像信息。", _GAP_PROFILE),
    "C112": ("EXERCISE", [EX], "", "否", _R_MULTITURN + "承接资料推荐，追加练习题。", ""),
    "C113": ("NORMAL_CHAT", [TQ], "", "否", _R_MULTITURN + "请求更通俗讲解。", ""),
    "C114": ("PLAN", [LP], "", "否", _R_MULTITURN + "调整既有学习路径顺序。", ""),
    "C115": ("VISUALIZATION", [VZ], "", "否", _R_MULTITURN + "把前文内容整理成图。", ""),

    # ---- C116-C130 复合任务 ----
    "C116": ("EXERCISE", [TQ, EX], f"{TQ}(1)>{EX}(2)", "是", _R_COMPOUND + "讲解+出题。", P("产品决策", "复合任务是否应顺序执行多中心，而非只保 gate 中心？")),
    "C117": ("EXERCISE", [TQ, EX], f"{TQ}(1)>{EX}(2)", "是", _R_COMPOUND + "讲解+练习。", P("产品决策", "复合任务多中心编排。")),
    "C118": ("EXERCISE", [TQ, EX], f"{TQ}(1)>{EX}(2)", "是", _R_COMPOUND + "讲解+出题。", P("产品决策", "复合任务多中心编排。")),
    "C119": ("PLAN", [LP, VZ], f"{LP}(1)>{VZ}(2)", "是", _R_COMPOUND + "计划+流程图。", P("产品决策", "跨中心（PLAN+VISUALIZATION）编排。")),
    "C120": ("RESOURCE", [RE, EX], f"{RE}(1)>{EX}(2)", "是", _R_COMPOUND + "讲义+练习。", P("产品决策", "跨中心（RESOURCE+EXERCISE）编排。")),
    "C121": ("VISUALIZATION", [TQ, VZ], f"{TQ}(1)>{VZ}(2)", "是", _R_COMPOUND + "讲解+配图。", P("产品决策", "复合任务多中心编排。")),
    "C122": ("PLAN", [DG, PB, LP], f"{DG}(1)>{PB}(2)>{LP}(3)", "是", _R_COMPOUND + "诊断+画像+计划，三中心链。", P("产品决策", "多中心链式编排 + 诊断/画像缺一级入口。")),
    "C123": ("EXERCISE", [SP, EX], f"{SP}(1)>{EX}(2)", "是", _R_COMPOUND + "解题+找类似题；solve_problem 与 exercise_gen 互斥。", P("路由算法", "互斥组 {solve_problem, exercise_gen} 会吞掉 solve_problem。")),
    "C124": ("VISUALIZATION", [VZ, EX], f"{VZ}(1)>{EX}(2)", "是", _R_COMPOUND + "思维导图+出题。", P("产品决策", "跨中心（VISUALIZATION+EXERCISE）编排。")),
    "C125": ("VISUALIZATION", [TQ, VZ], f"{TQ}(1)>{VZ}(2)", "是", _R_COMPOUND + "讲解+图示。", P("产品决策", "复合任务多中心编排。")),
    "C126": ("PLAN", [LP, RE], f"{LP}(1)>{RE}(2)", "是", _R_COMPOUND + "计划+资料。", P("产品决策", "跨中心（PLAN+RESOURCE）编排，且 {visualize,resource_gen} 邻近互斥需留意。")),
    "C127": ("EXERCISE", [EX, KG], f"{EX}(1)>{KG}(2)", "是", _R_COMPOUND + "出题+知识图谱。", P("产品决策", "跨中心（EXERCISE+VISUALIZATION）编排。")),
    "C128": ("RESOURCE", [TQ, CE], f"{TQ}(1)>{CE}(2)", "是", _R_COMPOUND + "讲解+代码示例。", P("产品决策", "code_example 缺一级入口 + 复合编排。")),
    "C129": ("EXERCISE", [DG, EX], f"{DG}(1)>{EX}(2)", "是", _R_COMPOUND + "诊断+针对性练习。", P("产品决策", "diagnose 缺一级入口 + 复合编排。")),
    "C130": ("PLAN", [RE, LP], f"{RE}(1)>{LP}(2)", "是", _R_COMPOUND + "资料+计划。", P("产品决策", "跨中心（RESOURCE+PLAN）编排。")),

    # ---- C131-C135 否定表达引用内容干扰 ----
    "C131": ("NORMAL_CHAT", [TQ], "", "否", _R_NEGATION + "明确否定出题，只要讲解。", P("路由算法", "gate 是否会被「出题」字面误触发 EXERCISE（应识别否定）。")),
    "C132": ("NORMAL_CHAT", [TQ], "", "否", _R_NEGATION + "明确否定画图，要文字说明。", P("路由算法", "gate 是否会被「画图」字面误触发 VISUALIZATION（应识别否定）。")),
    "C133": ("NORMAL_CHAT", [SP], "", "否", _R_NEGATION + "否定「怎么出题」，真实诉求=解这道题。", P("路由算法", "否定+转折表达下 solve_problem 被出题词压制。")),
    "C134": ("NORMAL_CHAT", [TQ], "", "否", _R_NEGATION + "否定资源推荐，要求讲清概念。", P("路由算法", "gate 是否会被「推荐资源」字面误触发 RESOURCE（应识别否定）。")),
    "C135": ("NORMAL_CHAT", [TQ], "", "否", _R_NEGATION + "「出题」在引号内为引用/转述，非本意。", P("路由算法", "引号内关键词是否应被 gate 排除（引用内容干扰）。")),

    # ---- C136-C140 空输入模糊请求缺少参数 ----
    "C136": ("待澄清", [], "", "是", _R_EMPTY + "空字符串。", P("产品决策", "空输入应触发澄清/引导，而非默认答疑。")),
    "C137": ("待澄清", [], "", "是", _R_EMPTY + "「嗯」无实质信息。", P("产品决策", "无信息短句应触发澄清。")),
    "C138": ("待澄清", [], "", "是", _R_EMPTY + "「帮我」为不完整祈使，缺宾语。", P("产品决策", "残缺祈使应追问补全参数。")),
    "C139": ("待澄清", [], "", "是", _R_EMPTY + "「在吗」为寒暄/探询。", P("产品决策", "寒暄语应引导表达诉求。")),
    "C140": ("待澄清", [], "", "是", _R_EMPTY + "「那个……就是那个」指代缺失。", P("产品决策", "指代缺失应追问。")),
}

COLUMNS = [
    "case_id", "category", "message", "mode",
    "suggested_capability", "suggested_intents", "suggested_task_order",
    "suggested_confirmation", "suggested_reason", "policy_question",
    "reviewer_decision",  # 留空，待人工裁决
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
            if cid not in SUGGEST:
                raise KeyError(f"未为该 case 定义建议：{cid}")
            cap, intents, order, confirm, reason, policy = SUGGEST[cid]
            rows.append({
                "case_id": cid,
                "category": o["category"],
                "message": o["message"],
                "mode": o["mode"],
                "suggested_capability": cap,
                "suggested_intents": "|".join(intents),
                "suggested_task_order": order,
                "suggested_confirmation": confirm,
                "suggested_reason": reason,
                "policy_question": policy,
                "reviewer_decision": "",
            })

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"rows={len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
