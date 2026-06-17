"""
BaseAgent -- 所有智能体的基类

参考 DeepTutor 的 BaseAgent 设计模式：
  - 统一的 LLM 配置管理
  - Prompt 从 YAML 文件加载（非硬编码）
  - 统一的流式和非流式 LLM 调用接口
  - 子类只需定义 system prompt 和 build_graph()

借鉴 OpenMAIC 的 buildPipeline：
  - {{snippet:name}} 片段复用
  - {{#if flag}}...{{/if}} 条件块
  - {variable} 变量插值
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from app.services.llm_service import create_llm, AgentModelProfile, ModelConfig
from app.utils.prompt_loader import build_prompt
from app.orchestration.agent_turn_summary import AgentTurnSummary


class BaseAgent(ABC):
    """所有智能体的抽象基类"""

    def __init__(
        self,
        agent_name: str,
        module: str = "agents",
        language: str = "zh",
        config: dict[str, Any] | None = None,
        use_mock_llm: bool = False,
        model_profile: AgentModelProfile | None = None,
    ):
        self.agent_name = agent_name
        self.module = module
        self.language = language
        self.config = config or {}
        self.use_mock_llm = use_mock_llm
        self._model_profile = model_profile
        self.system_prompt = self._load_prompt()

        if model_profile is not None:
            self.llm = self._build_llm(model_profile.default)
            if model_profile.plan is not None:
                self.plan_llm = self._build_llm(model_profile.plan)
        else:
            self.llm = create_llm(use_mock=use_mock_llm)

        self.logger = logging.getLogger(f"{module}.{agent_name}")
        self._compiled_graph = self.build_graph()

    def _load_prompt(
        self,
        filename: str = "system.yaml",
        variables: dict | None = None,
        key: str = "system",
    ) -> str:
        """加载 prompt 文件，支持 snippet / conditional / variable"""
        return build_prompt(
            self.agent_name,
            filename=filename,
            variables=variables,
            key=key,
        )

    def _load_extra_prompt(
        self,
        filename: str,
        variables: dict | None = None,
        key: str = "system",
    ) -> str:
        """加载额外的 prompt 文件（如 extract.yaml）"""
        return self._load_prompt(filename=filename, variables=variables, key=key)

    def _build_llm(self, config: ModelConfig) -> Any:
        """从 ModelConfig 构建 LLM 实例。"""
        return create_llm(
            model=config.model or None,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            use_mock=self.use_mock_llm,
            api_key=config.api_key,
            base_url=config.base_url,
        )

    @abstractmethod
    def build_graph(self) -> "CompiledStateGraph":
        """子类重写：定义 LangGraph 状态图"""
        raise NotImplementedError

    async def run(self, input_state: dict) -> dict:
        """执行智能体工作流（使用缓存的 compiled graph）"""
        return await self._compiled_graph.ainvoke(input_state)

    async def chat(self, messages: list[dict]) -> str:
        """非流式对话"""
        return await self.llm.chat(messages, system_prompt=self.system_prompt)

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式对话"""
        async for chunk in self.llm.chat_stream(
            messages, system_prompt=self.system_prompt
        ):
            yield chunk

    def create_turn_summary(
        self, state: dict, output: dict
    ) -> AgentTurnSummary:
        """从 agent 输出中提取结构化摘要。

        子类可 override 以提供更精准的提取逻辑。
        默认实现从常见字段中启发式提取 covered_concepts 和 generation_intent。
        """
        topic = state.get("topic", "")
        agent_name = self.__class__.__name__

        concepts = self._extract_concepts(output)
        intent = self._extract_intent(state, output)
        avoid = list(concepts[:4]) if concepts else []

        metrics = {}
        if "content_blocks" in output or "blocks" in output:
            blocks = output.get("content_blocks") or output.get("blocks") or []
            metrics["block_count"] = len(blocks)
        if "questions" in output:
            metrics["question_count"] = len(output["questions"])

        return AgentTurnSummary(
            agent_name=agent_name,
            topic=topic,
            covered_concepts=concepts,
            generation_intent=intent,
            avoid_duplicating=avoid,
            output_metrics=metrics,
        )

    @staticmethod
    def _extract_concepts(output: dict) -> list[str]:
        """从 output 中提取核心概念关键词"""
        concepts: list[str] = []

        outline = output.get("outline", {})
        if isinstance(outline, dict):
            subsections = outline.get("subsections", [])
            for sub in subsections[:8]:
                heading = sub.get("heading", "") if isinstance(sub, dict) else str(sub)
                if heading:
                    concepts.append(str(heading))

        if not concepts:
            blocks = output.get("blocks") or output.get("content_blocks") or []
            for b in blocks[:5]:
                heading = b.get("heading") or b.get("title") or ""
                if heading:
                    concepts.append(str(heading))

        return concepts[:8]

    @staticmethod
    def _extract_intent(state: dict, output: dict) -> str:
        """从 state/output 中提取生成意图"""
        topic = state.get("topic", "")
        if not topic:
            return ""

        block_count = 0
        blocks = output.get("blocks") or output.get("content_blocks") or []
        block_count = len(blocks)
        q_count = len(output.get("questions", []))

        if block_count > 2 and q_count > 0:
            return f"讲解{topic}的核心概念并提供练习题"
        elif block_count > 2:
            return f"讲解{topic}的核心概念和原理"
        elif q_count > 0:
            return f"为{topic}生成配套练习题"
        return f"围绕{topic}生成学习内容"

    @staticmethod
    def _format_profile(profile: dict) -> str:
        if not profile:
            return "（暂无学生画像，按默认难度生成）"
        lines = []
        labels = {
            "knowledge_base": "知识基础",
            "cognitive_style": "学习风格",
            "learning_goal": "学习目标",
            "weak_points": "薄弱环节",
            "learning_pace": "学习节奏",
            "interest_direction": "兴趣方向",
        }
        for key, label in labels.items():
            val = profile.get(key)
            if val is not None and val != []:
                if isinstance(val, list):
                    val = "、".join(str(v) for v in val)
                elif key == "knowledge_base":
                    val = f"{val}/100"
                lines.append(f"  - {label}: {val}")
        return "\n".join(lines) if lines else "（暂无学生画像，按默认难度生成）"

    async def _call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        expected_key: str | None = None,
        fallback: Any = None,
        max_retries: int = 1,
        validator: "Callable | None" = None,
        llm: "Any | None" = None,
    ) -> Any:
        """
        调用 LLM 并解析 JSON 返回。
        流程：调 LLM → 解析 JSON → validator 校验 → 注入 feedback 重试 → fallback

        validator: (result: dict) -> list[str]
          返回问题列表，空列表=通过。用于在重试时告诉 LLM 具体哪里不符合要求。
        llm: 可选，指定 LLM 实例（默认使用 self.llm）。用于需要不同 temperature 的场景。
        """
        if fallback is None:
            fallback = {}

        from app.utils.json_parser import parse_llm_json

        _llm = llm if llm is not None else self.llm
        last_raw = ""
        for attempt in range(max_retries + 1):
            try:
                messages = [{"role": "user", "content": user_prompt}]
                result_text = await _llm.chat(messages, system_prompt=system_prompt)
                last_raw = result_text
                result = parse_llm_json(result_text, fallback=fallback, expected_key=expected_key)

                if result == fallback:
                    if attempt < max_retries:
                        feedback = self._build_feedback(
                            last_raw, result, expected_key, None
                        )
                        user_prompt = self._append_feedback(user_prompt, feedback)
                        self.logger.warning(
                            f"LLM JSON parse returned fallback, retrying with feedback "
                            f"({attempt + 1}/{max_retries})"
                        )
                    continue

                # validator 检查
                if validator is not None:
                    issues = validator(result)
                    if issues:
                        if attempt < max_retries:
                            feedback = self._build_feedback(
                                last_raw, result, expected_key, issues
                            )
                            user_prompt = self._append_feedback(user_prompt, feedback)
                            self.logger.warning(
                                f"Validator found {len(issues)} issue(s), retrying with feedback "
                                f"({attempt + 1}/{max_retries})"
                            )
                            continue
                        else:
                            self.logger.warning(
                                f"Validator found {len(issues)} issue(s) on final attempt, "
                                f"returning as-is: {issues}"
                            )

                return result

            except (RuntimeError, ConnectionError) as e:
                self.logger.error(f"LLM call failed: {e}")
                if attempt < max_retries:
                    feedback = f"LLM 调用失败（{e}），请重新生成。"
                    user_prompt = self._append_feedback(user_prompt, feedback)
                    self.logger.info(f"Retrying LLM call ({attempt + 1}/{max_retries})")

        self.logger.error("All LLM JSON attempts failed, returning fallback")
        return fallback

    @staticmethod
    def _build_feedback(
        raw_text: str,
        parsed_result: Any,
        expected_key: str | None,
        issues: list[str] | None,
    ) -> str:
        """构造重试反馈消息，告诉 LLM 上一次输出哪里不符合要求。"""
        lines = ["上一次输出不符合要求："]
        preview = (raw_text or "").strip()
        if len(preview) > 500:
            preview = preview[:500].rstrip() + "\n...[已截断]"
        lines.append(f"\n你的上一次输出：\n```\n{preview}\n```")

        if expected_key is not None and isinstance(parsed_result, dict):
            actual_keys = list(parsed_result.keys()) if parsed_result else []
            if expected_key not in actual_keys:
                lines.append(
                    f"\n缺少必需字段 '{expected_key}'。"
                    f"实际得到字段: {actual_keys if actual_keys else '(空)'}"
                )

        if issues:
            lines.append("\n具体问题：")
            for i, issue in enumerate(issues, 1):
                lines.append(f"  {i}. {issue}")

        lines.append(f"\n请根据以上反馈修正输出，确保包含字段 '{expected_key}'。")
        return "\n".join(lines)

    @staticmethod
    def _append_feedback(original_prompt: str, feedback: str) -> str:
        """在原始 user prompt 末尾追加系统反馈。"""
        return f"{original_prompt}\n\n[系统反馈]\n{feedback}"
