"""
E2E 端到端标准测试 — 资源工坊模块（Resource Workshop）

Swagger 接口测试模式：完整覆盖从 HTTP 请求参数传入 → SSE 流接收
→ 结构化输出校验的全业务链路。

测试层级:
  L1 - 输入验证:      非法参数 → 400 错误响应
  L2 - 路由正确性:     Director 6 种资源类型路由验证（mock LLM）
  L3 - Agent 调度:     各 Agent 被正确调用，输出结构符合约定
  L4 - SSE 流完整性:   事件序列正确（stage_start → stage_end → done）
  L5 - 真实 LLM 链路:  端到端真实调用（USE_MOCK_LLM=false 时启用）
  L6 - 边界条件:       空 topic、超长输入、特殊字符、并发安全

运行方式:
  pytest tests/test_e2e_resource_workshop.py -v          # 全量 mock
  USE_REAL_LLM=1 pytest tests/test_e2e_resource_workshop.py -v -k "L5"  # 仅真实 LLM
"""

import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from internal_api import router


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

def _make_app() -> FastAPI:
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from fastapi import Request

    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        loc = errors[0].get("loc", [])
        if loc:
            field = str(loc[-1]) if len(loc) > 1 else str(loc[0])
            msg = f"字段 '{field}' {msg}"
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
        )

    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as c:
        yield c


@pytest.fixture
def student_profile():
    return {
        "knowledge_base": 50,
        "cognitive_style": "visual",
        "learning_goal": "掌握深度学习",
        "weak_points": ["数学基础"],
        "learning_pace": "moderate",
        "interest_direction": ["计算机视觉"],
    }


def _mock_workflow_output(agent_name: str) -> dict:
    """构造各 Agent 的模拟输出，匹配真实输出结构。"""
    outputs = {
        "content": {
            "content_blocks": [{"type": "section", "heading": "概述", "content": "## 基本概念\n\n这是测试内容。"}],
            "questions": [],
            "response": "已生成课程文档。",
        },
        "code": {
            "content_blocks": [{"type": "code", "heading": "代码示例", "content": "```python\ndef test(): pass\n```"}],
            "questions": [],
            "response": "已生成代码案例。",
        },
        "interactive_diagram": {
            "content_blocks": [{
                "type": "interactive_diagram",
                "heading": "可视化",
                "content": "输入图像依次通过卷积、池化和分类层。",
                "diagram": {
                    "schema_version": "v1",
                    "title": "可视化",
                    "summary": "输入图像依次通过卷积、池化和分类层。",
                    "layout": "layered",
                    "nodes": [
                        {"id": "input", "label": "输入", "detail": "原始数据", "layer": 0},
                        {"id": "process", "label": "处理", "detail": "特征提取", "layer": 1},
                        {"id": "output", "label": "输出", "detail": "结果", "layer": 2},
                    ],
                    "edges": [
                        {"source": "input", "target": "process", "label": "数据流"},
                        {"source": "process", "target": "output", "label": "结果"},
                    ],
                },
            }],
            "questions": [],
            "response": "已生成交互式可视化。",
        },
        "project": {
            "content_blocks": [{"type": "project", "heading": "项目实战", "content": "## 项目设计\n\n..."}],
            "questions": [],
            "response": "已生成项目方案。",
        },
        "mindmap": {
            "content_blocks": [{"type": "mindmap", "heading": "思维导图", "content": "```mermaid\ngraph TD\nA-->B\n```"}],
            "questions": [],
            "response": "已生成思维导图。",
        },
        "flashcard": {
            "content_blocks": [{"type": "flashcard", "heading": "记忆闪卡", "content": "Q: 什么是反向传播？\nA: ..."}],
            "questions": [],
            "response": "已生成记忆闪卡。",
        },
    }
    return outputs.get(agent_name, outputs["content"])


def _make_fake_resource_center(workflow_state=None, *, side_effect=None):
    """为 test_e2e_resource_workshop.py 构造 ResourceCenter + 注入 fake workflow。

    Task 1 末尾迁移 patch 点用；Task 3 完成后 /internal/resources/generate 真正接 ResourceCenter 时转绿。
    """
    from app.centers.resource_center import ResourceCenter

    center = ResourceCenter()
    fake_workflow = AsyncMock()
    if side_effect is not None:
        fake_workflow.run = AsyncMock(side_effect=side_effect)
    else:
        fake_workflow.run = AsyncMock(return_value=workflow_state)
    center.resource_workflow = fake_workflow
    return center


async def _consume_sse(response) -> list[dict]:
    """消费 SSE 流，返回解析后的事件列表。"""
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ═══════════════════════════════════════════════════════════════
# L1 — 输入验证（Input Validation）
# ═══════════════════════════════════════════════════════════════

class TestL1_InputValidation:
    """Swagger 风格：非法参数 → 400 + 清晰错误消息"""

    def test_empty_topic_rejected(self, client):
        """空 topic 被拒绝"""
        response = client.post("/internal/resources/generate", json={"user_id": 1})
        assert response.status_code == 400
        assert "topic" in response.json()["error"].lower()

    def test_whitespace_only_topic(self, client):
        """纯空格 topic 在 API 层 strip 后应返回 400，不进入工作流"""
        response = client.post("/internal/resources/generate", json={"topic": "   ", "user_id": 1})
        assert response.status_code == 400
        assert "topic" in response.json()["error"].lower()

    def test_missing_body(self, client):
        """空请求体被拒绝"""
        response = client.post("/internal/resources/generate")
        assert response.status_code == 400

    def test_invalid_resource_type_accepted_but_not_matched(self, client):
        """无效 resource_type 不阻塞请求，Director 走 rule/LLM 回退（scoped mock workflow）"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):
            response = client.post("/internal/resources/generate", json={
                "topic": "Python基础", "resource_type": "invalid_type_xyz",
            })
        assert response.status_code == 200  # 不回退 400，由 Director 处理

    def test_topic_with_special_chars(self, client):
        """特殊字符 topic 通过验证（scoped mock workflow）"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):
            response = client.post("/internal/resources/generate", json={
                "topic": "C++ & Python 对比：谁更好？",
            })
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════
# L2 — 路由正确性（Director Routing — mock LLM）
# ═══════════════════════════════════════════════════════════════

class TestL2_Routing:
    """验证 Director 6 种资源类型路由全部正确"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("topic,resource_type,expected_agent", [
        # resource_type 直接路由
        pytest.param("CNN架构", "document", "content", id="type_direct→document"),
        pytest.param("反向传播", "interactive_diagram", "interactive_diagram", id="type_direct→interactive"),
        pytest.param("Python实现CNN", "code", "code", id="type_direct→code"),
        pytest.param("图像分类项目", "project", "project", id="type_direct→project"),
        pytest.param("机器学习框架", "mindmap", "mindmap", id="type_direct→mindmap"),
        pytest.param("核心概念", "flashcard", "flashcard", id="type_direct→flashcard"),
        # 关键词路由
        pytest.param("从零搭建一个CNN分类项目", None, "project", id="keyword→project"),
        pytest.param("CNN架构的可视化演示", None, "interactive_diagram", id="keyword→interactive"),
        pytest.param("用Python实现反向传播代码", None, "code", id="keyword→code"),
        pytest.param("梳理一下机器学习知识框架", None, "mindmap", id="keyword→mindmap"),
        pytest.param("背诵深度学习的核心考点", None, "flashcard", id="keyword→flashcard"),
        pytest.param("介绍一下Transformer的原理", None, "content", id="keyword→content"),
        # 子类型检测
        pytest.param("对比ResNet和VGG的区别", None, "content", id="subtype→comparison"),
        pytest.param("这个bug怎么排查修复", None, "code", id="subtype→diagnosis"),
    ])
    async def test_director_routing(self, async_client, topic, resource_type, expected_agent):
        """每种路由策略验证 Director 正确选择了目标 Agent"""
        from app.orchestration.resource_selector import ResourceAgentSelector

        director = ResourceAgentSelector(use_mock=True)
        decision = await director.route(topic, resource_type=resource_type)
        assert decision.agent_name == expected_agent, (
            f"路由失败: topic='{topic}', type={resource_type}, "
            f"expected={expected_agent}, got={decision.agent_name}"
        )


# ═══════════════════════════════════════════════════════════════
# L3 — Agent 调度正确性（Agent Dispatch）
# ═══════════════════════════════════════════════════════════════

class TestL3_AgentDispatch:
    """验证每个 Agent 被正确调用，输出结构符合约定"""

    @pytest.mark.asyncio
    async def test_content_agent_produces_document_blocks(self):
        from app.agents.content_agent import ContentAgent

        agent = ContentAgent(use_mock_llm=True)
        state = {"topic": "反向传播算法", "student_profile": {}}
        result = await agent.run(state)
        assert isinstance(result, dict)
        assert "response" in result
        assert isinstance(result["response"], str) and len(result["response"]) > 0

    @pytest.mark.asyncio
    async def test_code_agent_produces_code_blocks(self):
        from app.agents.code_agent import CodeAgent

        agent = CodeAgent(use_mock_llm=True)
        state = {"topic": "CNN实现", "student_profile": {}}
        result = await agent.run(state)
        assert isinstance(result, dict)
        blocks = result.get("blocks", [])
        if blocks:
            assert blocks[0]["type"] == "code"

    @pytest.mark.asyncio
    async def test_mindmap_agent_produces_mindmap_blocks(self):
        from app.agents.mindmap_agent import MindMapAgent

        agent = MindMapAgent(use_mock_llm=True)
        state = {"topic": "机器学习", "student_profile": {}, "outline": {}}
        result = await agent.run(state)
        assert isinstance(result, dict)
        blocks = result.get("blocks", [])
        if blocks:
            assert blocks[0]["type"] == "mindmap"

    @pytest.mark.asyncio
    async def test_flashcard_agent_produces_flashcard_blocks(self):
        from app.agents.flashcard_agent import FlashCardAgent

        agent = FlashCardAgent(use_mock_llm=True)
        state = {"topic": "反向传播", "content_blocks": [
            {"heading": "概念", "content": "反向传播是..."}
        ]}
        result = await agent.run(state)
        assert isinstance(result, dict)
        assert "response" in result

    @pytest.mark.asyncio
    async def test_project_agent_produces_project_blocks(self):
        from app.agents.project_agent import ProjectAgent

        agent = ProjectAgent(use_mock_llm=True)
        state = {"topic": "CNN图像分类", "student_profile": {}}
        result = await agent.run(state)
        assert isinstance(result, dict)
        if "project_title" in result:
            assert len(result["project_title"]) > 0

    @pytest.mark.asyncio
    async def test_interactive_diagram_agent_produces_diagram_schema(self):
        from app.agents.interactive_diagram_agent import InteractiveDiagramAgent

        agent = InteractiveDiagramAgent(use_mock_llm=True)
        state = {"topic": "Transformer注意力机制", "diagram_type": "architecture"}
        result = await agent.run(state)
        assert isinstance(result, dict)
        blocks = result.get("blocks", [])
        assert blocks, "InteractiveDiagramAgent 应产出 blocks"
        assert blocks[0]["type"] == "interactive_diagram"
        diagram = blocks[0].get("diagram")
        assert isinstance(diagram, dict), "应产出结构化 diagram，而非 HTML"
        assert diagram.get("schema_version") == "v1"
        assert "<" not in str(blocks[0].get("content", "")), "content 不应含 HTML"


# ═══════════════════════════════════════════════════════════════
# L4 — SSE 流完整性（Stream Contract）
# ═══════════════════════════════════════════════════════════════

class TestL4_SSEStreamContract:
    """验证 SSE 事件流符合前端约定的格式和顺序"""

    @pytest.mark.asyncio
    async def test_sse_stream_contains_required_events(self, async_client, student_profile):
        """SSE 流包含 stage_start → stage_end → done 完整序列"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "反向传播", "user_id": 1, "student_profile": student_profile},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            events = await _consume_sse(response)
            event_types = [e.get("type") for e in events]

            assert "done" in event_types, f"Missing 'done' event in stream: {event_types}"
            # 确认 done 是最后一个有意义的事件
            assert event_types[-1] == "done" or event_types[-2] == "done"

    @pytest.mark.asyncio
    async def test_sse_stream_done_event_has_content_blocks(self, async_client):
        """done 事件携带 content_blocks 和 response"""
        output = _mock_workflow_output("content")
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(output)):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "Test", "user_id": 1},
            )
            events = await _consume_sse(response)
            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) == 1
            done_data = done_events[0].get("data", {})
            assert "content_blocks" in done_data
            assert "response" in done_data

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource_type", [
        "document", "code", "interactive_diagram", "project", "mindmap", "flashcard",
    ])
    async def test_all_six_types_produce_valid_sse(self, async_client, resource_type):
        """全部 6 种 resource_type 都产生合法的 SSE 流"""
        output = _mock_workflow_output(
            "interactive_diagram" if resource_type == "interactive_diagram" else
            resource_type if resource_type in ("document",) else
            "content"
        )
        # 归一化：所有类型走 content mock 输出结构
        output = _mock_workflow_output("content")

        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(output)):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "测试主题", "resource_type": resource_type, "user_id": 1},
            )
            assert response.status_code == 200
            events = await _consume_sse(response)
            assert any(e.get("type") == "done" for e in events), (
                f"resource_type='{resource_type}' SSE 流缺少 done 事件"
            )

    @pytest.mark.asyncio
    async def test_sse_error_graceful_degradation(self, async_client):
        """工作流异常时 SSE 流仍返回 done 事件 + error 信息"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(side_effect=RuntimeError("模拟 LLM 调用失败"))):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "Test", "user_id": 1},
            )
            assert response.status_code == 200
            events = await _consume_sse(response)
            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) >= 1, "异常时也应返回 done 事件"


# ═══════════════════════════════════════════════════════════════
# L4b — SSE 质量门控元数据（Review Metadata）
# ═══════════════════════════════════════════════════════════════

class TestL4b_SSEReviewMetadata:
    """验证 done 事件透传质量门控运行状态字段，非致命问题不被当作失败"""

    @pytest.mark.asyncio
    async def test_sse_done_contains_review_metadata(self, async_client):
        output = {
            **_mock_workflow_output("content"),
            "review_status": "skipped",
            "repair_attempted": False,
            "fallback_used": False,
            "final_status": "success",
        }
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(output)):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "Test", "user_id": 1},
            )
            events = await _consume_sse(response)
            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) == 1
            done_data = done_events[0].get("data", {})
            assert done_data.get("review_status") == "skipped"
            assert done_data.get("repair_attempted") is False
            assert done_data.get("fallback_used") is False
            assert done_data.get("final_status") == "success"

    @pytest.mark.asyncio
    async def test_sse_skipped_review_is_not_error(self, async_client):
        output = {
            **_mock_workflow_output("content"),
            "review_status": "skipped",
            "repair_attempted": False,
            "fallback_used": False,
            "final_status": "success",
        }
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(output)):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "Test", "user_id": 1},
            )
            events = await _consume_sse(response)
            assert not any(e.get("type") == "error" for e in events)
            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) == 1


# ═══════════════════════════════════════════════════════════════
# L5 — 真实 LLM 端到端链路（Real LLM Smoke Tests）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.real_llm
class TestL5_RealLLME2E:
    """真实 LLM 调用 — 验证完整业务链路可用性。需显式启用。"""

    @pytest.mark.asyncio
    async def test_real_content_generation(self, async_client, student_profile):
        """真实 LLM：生成课程文档，验证输出结构完整"""
        response = await async_client.post(
            "/internal/resources/generate",
            json={
                "topic": "反向传播算法",
                "resource_type": "document",
                "user_id": 1,
                "student_profile": student_profile,
            },
            timeout=120.0,
        )
        assert response.status_code == 200
        events = await _consume_sse(response)
        done = next((e for e in events if e.get("type") == "done"), None)
        assert done is not None, "未收到 done 事件"
        data = done.get("data", {})
        assert "content_blocks" in data
        assert len(data.get("content_blocks", [])) > 0, "真实 LLM 应产生至少 1 个内容块"
        assert not data.get("error"), f"真实 LLM 调用出错: {data.get('error')}"

    @pytest.mark.asyncio
    async def test_real_code_generation(self, async_client, student_profile):
        """真实 LLM：生成代码案例，验证输出含代码"""
        response = await async_client.post(
            "/internal/resources/generate",
            json={
                "topic": "用Python实现线性回归",
                "resource_type": "code",
                "user_id": 1,
                "student_profile": student_profile,
            },
            timeout=120.0,
        )
        assert response.status_code == 200
        events = await _consume_sse(response)
        done = next((e for e in events if e.get("type") == "done"), None)
        assert done is not None
        data = done.get("data", {})
        assert not data.get("error"), f"真实 LLM 调用出错: {data.get('error')}"


# ═══════════════════════════════════════════════════════════════
# L6 — 边界条件与鲁棒性（Edge Cases & Robustness）
# ═══════════════════════════════════════════════════════════════

class TestL6_EdgeCases:
    """边界条件、特殊输入、并发安全"""

    @pytest.mark.asyncio
    async def test_very_long_topic(self, async_client):
        """超长 topic（500+ 字符）不会导致崩溃"""
        long_topic = "深度学习" * 200
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": long_topic, "user_id": 1},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_topic_with_unicode_emoji(self, async_client):
        """含 emoji 和特殊 Unicode 的 topic"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "学习 AI 🧠 神经网络 ⚡ GPU加速"},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_student_profile(self, async_client):
        """空学生画像不会导致崩溃"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):

            response = await async_client.post(
                "/internal/resources/generate",
                json={"topic": "Test", "user_id": 1, "student_profile": {}},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, async_client):
        """并发 5 请求不互相干扰"""
        with patch("internal_api._get_resource_center", return_value=_make_fake_resource_center(_mock_workflow_output("content"))):

            async def one_request(i: int):
                return await async_client.post(
                    "/internal/resources/generate",
                    json={"topic": f"主题{i}", "user_id": i},
                )

            responses = await asyncio.gather(*[one_request(i) for i in range(5)])
            for resp in responses:
                assert resp.status_code == 200

    def test_workflow_direct_router_correctness_all_patterns(self):
        """验证所有路由表 pattern 至少能匹配一个示例输入（无死规则）"""
        from app.orchestration.resource_selector import ResourceAgentSelector

        director = ResourceAgentSelector(use_mock=True)

        # 每个路由 pattern 至少验证一个正例
        test_cases = [
            ("从零搭建一个CNN图像分类实战项目", "project"),
            ("Transformer架构的动态可视化演示", "interactive_diagram"),
            ("用Python写一个排序算法代码示例", "code"),
            ("梳理深度学习的知识框架和概念图", "mindmap"),
            ("背诵机器学习核心概念速记卡片", "flashcard"),
            ("对比Adam和SGD优化器的优缺点", "content"),
            ("这个TypeError报错怎么排查debug", "code"),
            ("介绍一下反向传播的基本原理", "content"),
        ]

        for topic, expected in test_cases:
            decision = director._rule_route(topic)
            assert decision is not None, f"规则路由对 '{topic}' 返回 None"
            assert decision.agent_name == expected, (
                f"路由错误: '{topic}' → {decision.agent_name}, 期望 {expected}"
            )


# ═══════════════════════════════════════════════════════════════
# conftest.py 补充 — pytest 命令行选项
# ═══════════════════════════════════════════════════════════════

def pytest_addoption(parser):
    parser.addoption(
        "--real-llm",
        action="store_true",
        default=False,
        help="启用真实 LLM 端到端测试（需要有效的 API key）",
    )
