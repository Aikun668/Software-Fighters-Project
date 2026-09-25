"""Internal API 包 — Architecture #2: Java → Python 纯 AI 推理。

原则：
- Java 把所有需要的数据放在请求体中传给 Python
- Python 只做 AI 计算，返回结果
- Python 不调 Java API，不持久化

结构（GUIDE P2 第 5 步「单文件 → 包」的拆包结果）：
- 本 `__init__.py` 是**薄壳**：依赖装配（惰性单例）+ 共享符 re-export + 聚合 router，
  **内不含任何路由实现**；48 个路由按业务域拆到同级子模块。
- 子模块引用可注入符号时应写 `api._get_xxx()`（调用时属性查找）。
  裸名会绑到子模块自己的模块全局，导致 `monkeypatch.setattr(internal_api, ...)`
  静默失效 —— 这是本次拆包最隐蔽的坑，由
  `tests/test_internal_api_package_contract.py::PKG-B04` 钉死。
"""

import logging
import os
import threading
from pathlib import Path

from fastapi import APIRouter

from app.api.errors import ErrorCode, api_error, api_success
from app.api.models import (
    CategorizeExerciseRequest,
    CompleteStepRequest,
    CreatePlanFromPathRequest,
    DashboardRequest,
    ErrorAnalysisRequest,
    EvaluationReportRequest,
    ExerciseGenRequest,
    ExportDocxRequest,
    ExportPdfRequest,
    ExportPptxRequest,
    GradeRequest,
    GraphExtractRequest,
    GraphLayeredRequest,
    GraphMermaidRequest,
    GraphNodesRequest,
    GraphPrerequisiteRequest,
    GraphProgressRequest,
    GraphReloadRequest,
    GraphSuggestEdgesRequest,
    InquiryResolveRequest,
    KnowledgeGraphNodeRequest,
    KnowledgeGraphRequest,
    MasteryUpdateRequest,
    NodeDeleteRequest,
    NodeStatusChangeRequest,
    NodeUpdateRequest,
    PlanStatusRequest,
    ProfileChatRequest,
    ProfileEnrichRequest,
    ProfileWorkflowStatusRequest,
    ProgressUpdateRequest,
    RegressionCheckRequest,
    ResourceGenRequest,
    ResourceLinkRequest,
    ReviewScheduleRequest,
    SessionAnalyzeRequest,
    SolveRequest,
    SummaryRequest,
    TodayTasksRequest,
    TutorChatRequest,
    UnifiedChatRequest,
)
from app.centers.chat_center import ChatCenter
from app.centers.plan_center import PlanCenter, PlanGenerationError, PlanNotFoundError
from app.centers.resource_center import ResourceCenter
from app.events.types import done_event, error_content_event
from app.services.intent_extractor import IntentExtractor
from app.utils.prompt_guard import sanitize_model
from app.utils.security_middleware import safe_export_path
from app.utils.sse_response import sse_response

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 依赖装配（惰性单例）
#
# 全包唯一允许构造 Center / Agent / Workflow / Service 的位置是下方各
# `_get_xxx()` 工厂；48 个端点无一例外经由它们取依赖。
#
# ⚠️ 注入点冻结（不得漂移）：
#   ① `internal_api._get_xxx`       —— 既有测试的 monkeypatch 目标（8 个名字）
#   ② `internal_api._xxx_singleton` —— 既有测试直改的状态变量（3 个变量）
#   ③ `inspect.getsource` 内的 `_get_xxx()` 字面文本（5 个测试文件）
# 三者都要求这些名字在本（包）命名空间可见；搬到别的模块会让注入点静默失效。
#
# 状态集中声明于此，按 (singleton, lock) 成对排列；工厂本体见各 _get_xxx。
# ═══════════════════════════════════════════════════════════════

_chat_center_singleton = None
_chat_center_lock = threading.Lock()

_profile_agent_singleton = None
_profile_agent_lock = threading.Lock()

_tutor_agent_singleton = None
_tutor_agent_lock = threading.Lock()

_content_agent_singleton = None
_content_agent_lock = threading.Lock()

_exercise_agent_singleton = None
_exercise_agent_lock = threading.Lock()

_exercise_center_singleton = None
_exercise_center_lock = threading.Lock()

_path_agent_singleton = None
_path_agent_lock = threading.Lock()

_mindmap_agent_singleton = None
_mindmap_agent_lock = threading.Lock()

_code_agent_singleton = None
_code_agent_lock = threading.Lock()

_profile_workflow_singleton = None
_profile_workflow_lock = threading.Lock()

_resource_center_singleton = None
_resource_center_lock = threading.Lock()

_path_workflow_singleton = None
_path_workflow_lock = threading.Lock()

_inquiry_service_singleton = None
_inquiry_service_lock = threading.Lock()

_tutor_center_singleton = None
_tutor_center_lock = threading.Lock()

_plan_center_singleton = None
_plan_center_lock = threading.Lock()

_graph_service_singleton = None
_graph_service_lock = threading.Lock()

_graph_center_singleton = None
_graph_center_lock = threading.Lock()

_intent_extractor: IntentExtractor | None = None
_intent_extractor_lock = threading.Lock()


def _get_chat_center():
    """API 层 ChatCenter 装配点；测试 patch 目标为 internal_api._get_chat_center。"""
    global _chat_center_singleton
    if _chat_center_singleton is None:
        with _chat_center_lock:
            if _chat_center_singleton is None:
                from app.centers.chat_center import ChatCenter
                _chat_center_singleton = ChatCenter()
    return _chat_center_singleton


def _get_mock_flag() -> bool:
    """是否用 mock LLM 构造 Agent（离线可跑）。

    P3-D 改造：由硬编码 `return False` 改为**环境变量开关** ——
    `AI_SERVICE_MOCK_LLM=1|true|yes|on` → True；未设置/其它值 → **False**（生产默认，
    与历史行为逐字一致，故零行为变化）。

    它同时是 13 个 `_get_xxx` 工厂能否在无 API key 环境构造成功的开关：
    置 True 时工厂走 mock LLM，离线可构造；离线测试现在可以
    `monkeypatch.setenv("AI_SERVICE_MOCK_LLM", "1")` 而不必 patch 本函数
    （旧手法仍有效，本函数保持 `internal_api` 命名空间下的可 patch 性）。
    """
    return os.getenv("AI_SERVICE_MOCK_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_profile_agent():
    """API 层 ProfileAgent 装配点；测试 patch 目标为 internal_api._get_profile_agent。"""
    global _profile_agent_singleton
    if _profile_agent_singleton is None:
        with _profile_agent_lock:
            if _profile_agent_singleton is None:
                from app.agents.profile_agent import ProfileAgent
                _profile_agent_singleton = ProfileAgent(use_mock_llm=_get_mock_flag())
    return _profile_agent_singleton


def _get_tutor_agent():
    """API 层 TutorAgent 装配点；测试 patch 目标为 internal_api._get_tutor_agent。"""
    global _tutor_agent_singleton
    if _tutor_agent_singleton is None:
        with _tutor_agent_lock:
            if _tutor_agent_singleton is None:
                from app.agents.tutor_agent import TutorAgent
                _tutor_agent_singleton = TutorAgent(use_mock_llm=_get_mock_flag())
    return _tutor_agent_singleton


def _get_tutor_center():
    """惰性单例工厂：答疑域唯一业务入口装配点。

    注入 API 层既有的 TutorAgent / ProfileAgent 单例，与收口前 /tutor/chat
    的构造一致；测试 patch 目标为 internal_api._get_tutor_center。
    """
    global _tutor_center_singleton
    if _tutor_center_singleton is None:
        with _tutor_center_lock:
            if _tutor_center_singleton is None:
                from app.centers.tutor_center import TutorCenter
                _tutor_center_singleton = TutorCenter(
                    tutor_agent=_get_tutor_agent(),
                    profile_agent=_get_profile_agent(),
                )
    return _tutor_center_singleton


def _get_content_agent():
    """API 层 ContentAgent 装配点；测试 patch 目标为 internal_api._get_content_agent。"""
    global _content_agent_singleton
    if _content_agent_singleton is None:
        with _content_agent_lock:
            if _content_agent_singleton is None:
                from app.agents.content_agent import ContentAgent
                _content_agent_singleton = ContentAgent(use_mock_llm=_get_mock_flag())
    return _content_agent_singleton


def _get_exercise_agent():
    """API 层 ExerciseAgent 装配点；测试 patch 目标为 internal_api._get_exercise_agent。"""
    global _exercise_agent_singleton
    if _exercise_agent_singleton is None:
        with _exercise_agent_lock:
            if _exercise_agent_singleton is None:
                from app.agents.exercise_agent import ExerciseAgent
                _exercise_agent_singleton = ExerciseAgent(use_mock_llm=_get_mock_flag())
    return _exercise_agent_singleton


def _get_exercise_center():
    """惰性单例工厂：练习域唯一业务入口装配点。

    装配的 ExerciseAgent 不带 model_profile，与收口前 /exercise/generate 与
    complete-step 的构造一致；聊天侧 ExerciseCenter.execute() 的惰性默认
    （PROFILE_EXERCISE）不受影响。
    测试 patch 目标为 internal_api._get_exercise_center。
    """
    global _exercise_center_singleton
    if _exercise_center_singleton is None:
        with _exercise_center_lock:
            if _exercise_center_singleton is None:
                from app.agents.solve_agent import SolveAgent
                from app.centers.exercise_center import ExerciseCenter
                _exercise_center_singleton = ExerciseCenter(
                    exercise_agent=_get_exercise_agent(),
                    solve_agent=SolveAgent(use_mock_llm=_get_mock_flag()),
                )
    return _exercise_center_singleton


def _get_path_agent():
    """API 层 PathAgent 装配点；测试 patch 目标为 internal_api._get_path_agent。"""
    global _path_agent_singleton
    if _path_agent_singleton is None:
        with _path_agent_lock:
            if _path_agent_singleton is None:
                from app.agents.path_agent import PathAgent
                _path_agent_singleton = PathAgent(use_mock_llm=_get_mock_flag())
    return _path_agent_singleton


def _get_mindmap_agent():
    """API 层 MindMapAgent 装配点；测试 patch 目标为 internal_api._get_mindmap_agent。"""
    global _mindmap_agent_singleton
    if _mindmap_agent_singleton is None:
        with _mindmap_agent_lock:
            if _mindmap_agent_singleton is None:
                from app.agents.mindmap_agent import MindMapAgent
                _mindmap_agent_singleton = MindMapAgent(use_mock_llm=_get_mock_flag())
    return _mindmap_agent_singleton


def _get_code_agent():
    """API 层 CodeAgent 装配点；测试 patch 目标为 internal_api._get_code_agent。"""
    global _code_agent_singleton
    if _code_agent_singleton is None:
        with _code_agent_lock:
            if _code_agent_singleton is None:
                from app.agents.code_agent import CodeAgent
                _code_agent_singleton = CodeAgent(use_mock_llm=_get_mock_flag())
    return _code_agent_singleton


def _get_profile_workflow():
    """API 层 ProfileWorkflow 装配点；测试 patch 目标为 internal_api._get_profile_workflow。"""
    global _profile_workflow_singleton
    if _profile_workflow_singleton is None:
        with _profile_workflow_lock:
            if _profile_workflow_singleton is None:
                from app.workflows.profile_workflow import ProfileWorkflow
                _profile_workflow_singleton = ProfileWorkflow(use_mock=_get_mock_flag())
    return _profile_workflow_singleton


def _get_resource_center() -> ResourceCenter:
    """资源域唯一业务入口工厂（API 层唯一允许装配 ResourceGenWorkflow 的位置）。

    返回单例 ResourceCenter(resource_workflow=ResourceGenWorkflow(use_mock=_get_mock_flag()))。
    API 路由不再直接获取 ResourceGenWorkflow；测试 patch 目标为 internal_api._get_resource_center。
    """
    global _resource_center_singleton
    if _resource_center_singleton is None:
        with _resource_center_lock:
            if _resource_center_singleton is None:
                from app.workflows.resource_gen import ResourceGenWorkflow
                _resource_center_singleton = ResourceCenter(
                    resource_workflow=ResourceGenWorkflow(use_mock=_get_mock_flag()),
                )
    return _resource_center_singleton


def _get_path_workflow():
    """API 层 LearningPathWorkflow 装配点；测试 patch 目标为 internal_api._get_path_workflow。"""
    global _path_workflow_singleton
    if _path_workflow_singleton is None:
        with _path_workflow_lock:
            if _path_workflow_singleton is None:
                from app.workflows.learning_path import LearningPathWorkflow
                _path_workflow_singleton = LearningPathWorkflow(use_mock=_get_mock_flag())
    return _path_workflow_singleton


def _get_inquiry_service():
    """API 层 InquiryService 装配点；测试 patch 目标为 internal_api._get_inquiry_service。"""
    global _inquiry_service_singleton
    if _inquiry_service_singleton is None:
        with _inquiry_service_lock:
            if _inquiry_service_singleton is None:
                from app.services.inquiry_service import InquiryService
                _inquiry_service_singleton = InquiryService()
    return _inquiry_service_singleton


def _get_plan_center():
    """惰性单例工厂：构造 PlanCenter 并装配 Goal/Decompose/Schedule Agent。

    该工厂是 API 层与 PlanCenter 之间的唯一依赖装配点。
    graph_service / step_classifier 留 None，由 PlanCenter 走现网 fallback。
    测试 patch 目标为 internal_api._get_plan_center。
    """
    global _plan_center_singleton
    if _plan_center_singleton is None:
        with _plan_center_lock:
            if _plan_center_singleton is None:
                from app.agents.goal_agent import GoalAgent
                from app.agents.decompose_agent import DecomposeAgent
                from app.agents.schedule_agent import ScheduleAgent
                from app.centers.plan_center import PlanCenter

                mock = _get_mock_flag()
                _plan_center_singleton = PlanCenter(
                    goal_agent=GoalAgent(use_mock_llm=mock),
                    decompose_agent=DecomposeAgent(use_mock_llm=mock),
                    schedule_agent=ScheduleAgent(use_mock_llm=mock),
                    exercise_center=_get_exercise_center(),
                )
    return _plan_center_singleton


def _get_graph_service():
    """API 层 GraphService 装配点；测试 patch 目标为 internal_api._get_graph_service。"""
    global _graph_service_singleton
    if _graph_service_singleton is None:
        with _graph_service_lock:
            if _graph_service_singleton is None:
                from app.services.graph_service import get_graph_service
                _graph_service_singleton = get_graph_service()
    return _graph_service_singleton


def _get_graph_center():
    """惰性单例工厂：图谱域唯一业务入口装配点。

    graph_service 注入外层包装 `_get_graph_service()`（与收口前的取用来源一致）；
    plan_service / extraction 留 None，由 GraphCenter 走惰性默认。
    该工厂是 API 层与 GraphCenter 之间的唯一依赖装配点。
    测试 patch 目标为 internal_api._get_graph_center。
    """
    global _graph_center_singleton
    if _graph_center_singleton is None:
        with _graph_center_lock:
            if _graph_center_singleton is None:
                from app.centers.graph_center import GraphCenter
                _graph_center_singleton = GraphCenter(
                    graph_service=_get_graph_service()
                )
    return _graph_center_singleton


def _get_intent_extractor() -> IntentExtractor:
    """API 层 IntentExtractor 装配点；测试 patch 目标为 internal_api._get_intent_extractor。

    注：聊天分流已收口进 ChatCenter，当前无路由直接调用本工厂；保留它是为了
    维持装配契约（`ASM-C02` / `ASM-S01` 等按 18 个工厂枚举）。
    """
    global _intent_extractor
    if _intent_extractor is None:
        with _intent_extractor_lock:
            if _intent_extractor is None:
                _intent_extractor = IntentExtractor()
    return _intent_extractor


# ═══════════════════════════════════════════════════════════════
# 导出目录（导出端点与下载守卫共用）
#
# 拆包前 `internal_api.py` 在 `ai-service/`，`dirname(__file__)` 即 `ai-service/`；
# 拆包后本文件在 `ai-service/internal_api/`，故上跳一级，保证导出目录**仍是**
# `ai-service/exports`（路径行为零变化）。
# ═══════════════════════════════════════════════════════════════

_EXPORTS_DIR = str(Path(__file__).resolve().parent.parent / "exports")


# ═══════════════════════════════════════════════════════════════
# 路由聚合
#
# 每个子模块自带一个**无前缀** `APIRouter`，此处统一挂到 `/internal` 前缀下。
# 子模块在本文件底部导入：那时 `router` 与装配区块均已就绪，且子模块内部
# `import internal_api as api` 能拿到已注册的模块对象（避免循环导入）。
# ═══════════════════════════════════════════════════════════════

router = APIRouter(prefix="/internal")

from . import (  # noqa: E402
    chat,
    eval_api,
    exercise,
    graph,
    inquiry,
    plans,
    profile,
    resources,
    tutor,
)

router.include_router(profile.router)
router.include_router(resources.router)
router.include_router(tutor.router)
router.include_router(chat.router)
router.include_router(exercise.router)
router.include_router(graph.router)
router.include_router(plans.router)
router.include_router(inquiry.router)
router.include_router(eval_api.router)

# ── re-export ────────────────────────────────────────────────────
# 既有测试以 `getattr(internal_api, name)` / `inspect.getsource(...)` 引用路由函数；
# 拆包后它们仍是本包命名空间的属性。同时 re-export `_sse_stream_chunks`。
from ._helpers import _sse_stream_chunks  # noqa: E402,F401
from .chat import _unified_chat, get_conversation_summary, unified_chat  # noqa: E402
from .eval_api import JudgeRequest, eval_judge  # noqa: E402
from .exercise import (  # noqa: E402
    analyze_session,
    categorize_exercises,
    enrich_profile,
    exercise_dashboard,
    exercise_error_analysis,
    exercise_generate,
    get_evaluation_report,
    grade_exercise,
    solve_question,
)
from .graph import (  # noqa: E402
    check_prerequisites,
    delete_node,
    export_mermaid,
    get_knowledge_graph,
    get_layered_graph,
    get_node_card,
    get_progress_summary,
    graph_extract,
    graph_nodes,
    recommend_next_node,
    reload_graph,
    suggest_edges,
    update_masteries,
    update_node,
)
from .inquiry import inquiry_resolve, inquiry_resolve_plan  # noqa: E402
from .plans import (  # noqa: E402
    complete_plan_step,
    create_plan_from_path,
    get_plan_status,
    get_plan_status_legacy,
    get_review_schedule,
    get_today_tasks,
    learning_path,
    on_node_status_change,
    regression_check,
    update_plan_progress,
)
from .profile import profile_chat, profile_workflow_status  # noqa: E402
from .resources import (  # noqa: E402
    download_docx,
    download_pdf,
    download_pptx,
    export_docx,
    export_pdf,
    export_pptx,
    resources_generate,
)
from .tutor import tutor_chat  # noqa: E402
