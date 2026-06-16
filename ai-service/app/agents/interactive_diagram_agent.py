"""InteractiveDiagramAgent — 交互式可视化生成智能体

生成自包含 HTML 文件，使用 D3.js / SVG / Canvas 渲染 AI 课程相关的
交互式可视化：模型架构、训练动态、注意力流、特征空间、算法步骤。
前端通过 sandboxed iframe 渲染输出。
"""

import html as _html
import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

DIAGRAM_TYPES = {
    "architecture": "模型架构图 — 展示网络层级结构、张量维度变化、数据流动方向",
    "training_dynamics": "训练动态 — 损失曲线、准确率变化、梯度分布随 epoch 的变化",
    "attention": "注意力流 — 自注意力权重热力图、跨注意力连接、token 间关系",
    "feature_space": "特征空间 — PCA/t-SNE 降维可视化、决策边界、聚类分布",
    "algorithm": "算法步骤 — 逐层/逐步骤演示算法执行过程，支持步骤前进/后退",
}


class InteractiveDiagramState(TypedDict, total=False):
    topic: str
    diagram_type: str
    student_profile: dict
    html_content: str
    description: str
    response: str


class InteractiveDiagramAgent(BaseAgent):
    """交互式可视化 Agent — 输出 interactive_diagram 类型 block"""

    def __init__(self, config=None, use_mock_llm: bool = False,
                 model_profile=None):
        super().__init__(
            agent_name="interactive_diagram_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(InteractiveDiagramState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    @staticmethod
    def _validate_html(result: dict) -> list[str]:
        issues = []
        html = result.get("html_content", "")
        if not isinstance(html, str) or len(html.strip()) < 100:
            issues.append("html_content 过短（<100 字符），不是有效的 HTML 文件")
            return issues
        html_lower = html.lower()
        has_svg = "svg" in html_lower and ("<svg" in html_lower or "<circle" in html_lower or "<rect" in html_lower or "<path" in html_lower)
        has_canvas = "canvas" in html_lower and ("<canvas" in html_lower or "getcontext" in html_lower)
        has_d3 = "d3" in html_lower and (".select" in html_lower or ".data" in html_lower or ".append" in html_lower)
        has_script_with_viz = "<script" in html_lower and (".select" in html_lower or ".data" in html_lower or "svg" in html_lower or "canvas" in html_lower or "d3" in html_lower)
        if not (has_svg or has_canvas or has_d3 or has_script_with_viz):
            issues.append("HTML 未包含有效的可视化组件（SVG 元素 / Canvas API / D3 API 调用）")
        return issues

    async def _generate_node(self, state: InteractiveDiagramState) -> dict:
        topic = state.get("topic", "")
        diagram_type = state.get("diagram_type", "architecture")
        student_profile = state.get("student_profile", {})

        if diagram_type not in DIAGRAM_TYPES:
            diagram_type = "architecture"

        type_desc = DIAGRAM_TYPES[diagram_type]

        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "diagram_type": diagram_type,
                "type_description": type_desc,
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="html_content",
            fallback={},
            validator=self._validate_html,
        )

        html_content = result.get("html_content", "") if result else ""
        description = result.get("description", "") if result else ""

        if not html_content:
            html_content, description = self._fallback_html(topic, diagram_type)
        else:
            html_content = self._sanitize_html_output(html_content)
            description = _html.escape(description) if description else ""

        blocks = [{
            "type": "interactive_diagram",
            "heading": f"{topic} — 交互式可视化",
            "content": html_content,
            "description": description,
            "diagram_type": diagram_type,
        }]

        logger.info(
            f"InteractiveDiagramAgent generated {diagram_type} "
            f"({len(html_content)} chars) for topic '{topic}'"
        )
        return {
            "blocks": blocks,
            "response": f"已生成「{topic}」的交互式可视化演示。",
            "html_content": html_content,
            "description": description,
        }

    @staticmethod
    def _sanitize_html_output(html_content: str) -> str:
        """移除 LLM 生成 HTML 中的 XSS 向量。先 HTML 解码后再清理，防止编码绕过。"""
        import html as _h
        # 先做一轮 HTML 实体解码，防止 &#99;lick 等编码绕过
        decoded = _h.unescape(html_content)
        # 移除危险标签及其内容
        for tag in ("script", "iframe", "object", "embed", "meta", "link", "base", "form"):
            decoded = re.sub(rf'<\s*{tag}\b[^>]*>.*?<\s*/\s*{tag}\s*>', '', decoded, flags=re.IGNORECASE | re.DOTALL)
            decoded = re.sub(rf'<\s*{tag}\b[^>]*/?\s*>', '', decoded, flags=re.IGNORECASE)
        # 移除 on* 事件处理器属性
        decoded = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', decoded, flags=re.IGNORECASE)
        decoded = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', decoded, flags=re.IGNORECASE)
        # 移除 javascript: / data:text/html: URI
        decoded = re.sub(r'(javascript|data\s*:\s*text/html)\s*:', '', decoded, flags=re.IGNORECASE)
        return decoded

    @staticmethod
    def _fallback_html(topic: str, diagram_type: str) -> tuple[str, str]:
        """静态 fallback — 构造一个简单的 SVG 占位图"""
        escaped_topic = _html.escape(topic)
        description = (
            f"「{escaped_topic}」的{DIAGRAM_TYPES.get(diagram_type, '可视化')}演示。"
            f"由于生成受限，当前为简化版本，建议刷新重试。"
        )
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_topic} — 交互式可视化</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px;
         background: #0f172a; color: #e2e8f0; display: flex;
         flex-direction: column; align-items: center; }}
  h2 {{ color: #38bdf8; margin-bottom: 8px; }}
  p {{ color: #94a3b8; margin-bottom: 24px; }}
  svg {{ background: #1e293b; border-radius: 12px; }}
  .node {{ fill: #38bdf8; stroke: #0f172a; stroke-width: 2; cursor: pointer; }}
  .node:hover {{ fill: #818cf8; }}
  .edge {{ stroke: #475569; stroke-width: 2; }}
  text.label {{ fill: #e2e8f0; font-size: 13px; text-anchor: middle;
                  dominant-baseline: central; pointer-events: none; }}
</style>
</head>
<body>
<h2>{escaped_topic} — 交互式可视化</h2>
<p>{_html.escape(description)}</p>
<div id="tooltip" style="display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
     background:#1e293b;color:#e2e8f0;padding:8px 16px;border-radius:8px;border:1px solid #38bdf8;z-index:100;"></div>
<svg width="600" height="400" viewBox="0 0 600 400">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5"
            orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#475569"/></marker>
  </defs>
  <line x1="100" y1="200" x2="230" y2="120" class="edge" marker-end="url(#arrow)"/>
  <line x1="100" y1="200" x2="230" y2="280" class="edge" marker-end="url(#arrow)"/>
  <line x1="350" y1="120" x2="480" y2="160" class="edge" marker-end="url(#arrow)"/>
  <line x1="350" y1="200" x2="480" y2="200" class="edge" marker-end="url(#arrow)"/>
  <line x1="350" y1="280" x2="480" y2="240" class="edge" marker-end="url(#arrow)"/>
  <circle cx="100" cy="200" r="36" class="node" id="input"/>
  <text x="100" y="200" class="label">输入</text>
  <circle cx="230" cy="120" r="36" class="node" id="layer1"/>
  <text x="230" y="120" class="label">层 1</text>
  <circle cx="230" cy="280" r="36" class="node" id="layer1b"/>
  <text x="230" y="280" class="label">层 2</text>
  <circle cx="350" cy="120" r="36" class="node" id="hidden1"/>
  <text x="350" y="120" class="label">隐藏 1</text>
  <circle cx="350" cy="200" r="36" class="node" id="hidden2"/>
  <text x="350" y="200" class="label">隐藏 2</text>
  <circle cx="350" cy="280" r="36" class="node" id="hidden3"/>
  <text x="350" y="280" class="label">隐藏 3</text>
  <circle cx="480" cy="200" r="36" class="node" id="output"/>
  <text x="480" y="200" class="label">输出</text>
</svg>
<script>
  document.querySelectorAll('.node').forEach(node => {{
    node.addEventListener('click', () => {{
      const info = document.getElementById('tooltip');
      if (info) {{
        info.textContent = '节点: ' + (node.id || '未命名');
        info.style.display = 'block';
        setTimeout(() => {{ info.style.display = 'none'; }}, 2000);
      }}
    }});
  }});
</script>
</body>
</html>"""
        return html, description
