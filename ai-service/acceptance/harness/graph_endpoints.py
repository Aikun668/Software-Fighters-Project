#!/usr/bin/env python3
"""图谱域收口字节存证：同进程 ASGI 打 14 个图谱端点，输出原始响应体 + sha256。

用法（在 ai-service 目录）：
    python _accept_graph_endpoints.py before
    python _accept_graph_endpoints.py after

在同一 commit 上重跑应得到完全相同的 sha256；跨「收窄前 4d77614 / 收窄后」
两个 commit 重跑，sha256 全等即证明响应字节零变化。

设计要点（为了「同一份脚本在两个 commit 上都能跑出结果」）：
- 每打一个用例前都把 GraphService 换成全新实例：GraphService 是有状态内存
  单例（add_node/add_edge/delete_node/update_node 只改 _skeleton_cache），
  不复位就会让后面的用例读到前面用例的变异。
- 三条单例路径都要复位：internal_api._graph_service_singleton（13 个路由的
  外层包装）、app.services.graph_service._graph_service（/graph/reload 收口前
  直连的内层工厂）、internal_api._graph_center_singleton（收窄后 GraphCenter
  在构造时抓住的实例；收窄前该属性不存在，setattr 一个多余的模块属性无害）。
- 抽取注入点**双打**（internal_api.extract_knowledge_nodes +
  app.services.knowledge_extraction.extract_knowledge_nodes）：收口前调用点在
  前者，收口后在后者的模块属性上现取，只打一处会让某个 commit 上真调 LLM。
- 补边建议注入 GraphService.suggest_edges 类方法（收窄前后同一注入点）。
- 全程不触网、无时间依赖（掌握度是纯公式，节点卡片的时间戳由请求体给定）。
"""

import asyncio
import hashlib
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import app.services.graph_service as graph_service_module
import app.services.knowledge_extraction as knowledge_extraction_module
import internal_api
from app.services.graph_service import GraphService
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from internal_api import router

EXTRACT_GROUPS = {
    "primary": [{"node_id": "overfitting", "name": "过拟合与正则化", "confidence": 0.91}],
    "related": [{"node_id": "gradient_variants", "name": "梯度下降变体", "confidence": 0.72}],
    "broad": [{"node_id": "ml_basics", "name": "机器学习基础", "confidence": 0.55}],
    "all": [
        {"node_id": "overfitting", "name": "过拟合与正则化", "confidence": 0.91},
        {"node_id": "gradient_variants", "name": "梯度下降变体", "confidence": 0.72},
        {"node_id": "ml_basics", "name": "机器学习基础", "confidence": 0.55},
    ],
}

EXTRACT_GROUPS_PARTIAL = {"primary": [{"node_id": "overfitting", "confidence": 0.9}]}

SUGGESTIONS = [
    {"source": "overfitting", "target": "cnn", "relation": "depends_on",
     "rationale": "正则化影响卷积网络训练"},
    {"source": "nlp_llm", "target": "self_attention", "relation": "parallel",
     "rationale": "共同前置: transformer"},
]


async def _fixed_extraction(*, course_id, user_message, assistant_reply,
                            existing_node_ids=None):
    if "partial" in user_message:
        return dict(EXTRACT_GROUPS_PARTIAL)
    return {k: [dict(item) for item in v] for k, v in EXTRACT_GROUPS.items()}


async def _fixed_suggest_edges(self, course_id=None):
    return [dict(item) for item in SUGGESTIONS]


def _install_stubs() -> None:
    knowledge_extraction_module.extract_knowledge_nodes = _fixed_extraction
    internal_api.extract_knowledge_nodes = _fixed_extraction
    GraphService.suggest_edges = _fixed_suggest_edges


def _reset_state() -> None:
    fresh = GraphService()
    internal_api._graph_service_singleton = fresh
    graph_service_module._graph_service = fresh
    internal_api._graph_center_singleton = None


def _masteries(**over) -> dict:
    base = {"ai_overview": 0.9, "ml_basics": 0.6, "dl_basics": 0.2}
    base.update(over)
    return base


CASES = [
    # ── 读路径 ───────────────────────────────────────────────────
    ("kg-get-graph", "POST", "/internal/knowledge-graph/ai_intro",
     {"masteries": _masteries()}),
    ("kg-get-graph-empty-masteries", "POST", "/internal/knowledge-graph/ai_intro", {}),
    ("kg-node-card", "POST", "/internal/knowledge-graph/ai_intro/node/ai_overview",
     {"masteries": _masteries(), "total_exercises": 7,
      "last_practiced": "2026-09-01T00:00:00Z"}),
    ("kg-node-card-not-found", "POST", "/internal/knowledge-graph/ai_intro/node/nope",
     {"masteries": {}}),
    ("graph-next-node", "POST", "/internal/graph/next-node",
     {"course_id": "ai_intro", "masteries": _masteries()}),
    ("graph-progress", "POST", "/internal/graph/progress",
     {"course_id": "ai_intro", "masteries": _masteries(ml_basics=1.0)}),
    ("graph-check-prerequisites", "POST", "/internal/graph/check-prerequisites",
     {"course_id": "ai_intro", "node_id": "dl_basics",
      "masteries": _masteries(), "threshold": 0.5}),
    ("graph-export-mermaid", "POST", "/internal/graph/export-mermaid",
     {"course_id": "ai_intro", "masteries": _masteries()}),
    ("graph-layered", "POST", "/internal/graph/layered",
     {"course_id": "ai_intro", "masteries": _masteries()}),
    ("graph-suggest-edges", "POST", "/internal/graph/suggest-edges",
     {"course_id": "ai_intro"}),
    # ── 抽取 ─────────────────────────────────────────────────────
    ("graph-extract", "POST", "/internal/graph/extract",
     {"course_id": "ai_intro", "user_message": "什么是过拟合",
      "assistant_reply": "过拟合指模型在训练集上表现过好",
      "existing_node_ids": ["backprop"]}),
    ("graph-extract-partial", "POST", "/internal/graph/extract",
     {"course_id": "ai_intro", "user_message": "partial", "assistant_reply": "a"}),
    # ── 写路径 ───────────────────────────────────────────────────
    ("graph-nodes-add", "POST", "/internal/graph/nodes",
     {"course_id": "ai_intro", "updates": [
         {"action": "add_node", "data": {"id": "dyn_acc", "name": "动态节点",
                                         "difficulty": 4}},
         {"action": "add_edge", "data": {"source": "ai_overview",
                                         "target": "dyn_acc"}},
     ]}),
    ("graph-nodes-duplicate-400", "POST", "/internal/graph/nodes",
     {"course_id": "ai_intro", "updates": [
         {"action": "add_node", "data": {"id": "ai_overview"}},
     ]}),
    ("graph-nodes-empty-updates", "POST", "/internal/graph/nodes",
     {"course_id": "ai_intro", "updates": []}),
    ("graph-masteries", "POST", "/internal/graph/masteries",
     {"course_id": "ai_intro", "masteries": {"ml_basics": 0.5},
      "events": [
          {"node_id": "ml_basics", "event_type": "exercise_done", "score": 0.8},
          {"node_id": "ml_basics", "event_type": "resource_viewed"},
          {"node_id": "dl_basics", "event_type": "exercise_failed"},
          {"node_id": "cnn", "event_type": "tutor_question_asked"},
      ]}),
    ("graph-masteries-empty-events-400", "POST", "/internal/graph/masteries",
     {"course_id": "ai_intro", "masteries": {}, "events": []}),
    ("graph-reload", "POST", "/internal/graph/reload", {}),
    ("graph-node-delete-400-skeleton", "POST",
     "/internal/graph/nodes/ai_overview/delete", {"course_id": "ai_intro"}),
    ("graph-node-update-400-skeleton", "POST",
     "/internal/graph/nodes/ai_overview/update",
     {"course_id": "ai_intro", "updates": {"name": "改名"}}),
]

# 依赖前置变异的用例：先加一个动态节点，再删/改它（单独一组，保证可复现）
CHAINED_CASES = [
    ("graph-node-delete-dynamic", [
        ("POST", "/internal/graph/nodes", {"course_id": "ai_intro", "updates": [
            {"action": "add_node", "data": {"id": "dyn_del", "name": "待删"}},
        ]}),
        ("POST", "/internal/graph/nodes/dyn_del/delete", {"course_id": "ai_intro"}),
    ]),
    ("graph-node-update-dynamic", [
        ("POST", "/internal/graph/nodes", {"course_id": "ai_intro", "updates": [
            {"action": "add_node", "data": {"id": "dyn_upd", "name": "待改"}},
        ]}),
        ("POST", "/internal/graph/nodes/dyn_upd/update",
         {"course_id": "ai_intro", "updates": {"name": "改名后", "difficulty": 5}}),
    ]),
    ("graph-reload-wipes-mutations", [
        ("POST", "/internal/graph/nodes", {"course_id": "ai_intro", "updates": [
            {"action": "add_node", "data": {"id": "dyn_wipe", "name": "将被抹掉"}},
        ]}),
        ("POST", "/internal/graph/reload", {}),
        ("POST", "/internal/knowledge-graph/ai_intro", {"masteries": {}}),
    ]),
]


async def main(label: str) -> int:
    _install_stubs()
    app = FastAPI()
    app.include_router(router)

    blocks = []
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept",
    ) as client:
        for name, method, path, body in CASES:
            _reset_state()
            response = await client.request(method, path, json=body)
            raw = response.text
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            blocks.append(
                f"### {name} {method} {path}\n"
                f"status={response.status_code}\n"
                f"sha256={digest}\n"
                f"{raw}\n"
            )

        for name, steps in CHAINED_CASES:
            _reset_state()
            trace = []
            for step_no, (method, path, body) in enumerate(steps, start=1):
                response = await client.request(method, path, json=body)
                raw = response.text
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                trace.append(
                    f"  [step{step_no}] {method} {path}\n"
                    f"  status={response.status_code}\n"
                    f"  sha256={digest}\n"
                    f"{raw}\n"
                )
            blocks.append(f"### {name} (chained)\n" + "\n".join(trace))

    report = "\n".join(blocks)
    with open(f"_accept_graph_endpoints_{label}.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
