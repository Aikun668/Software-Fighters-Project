"""
增强版 Prompt 加载器

借鉴 OpenMAIC lib/prompts/loader.ts 的 buildPipeline：
  load YAML → processSnippets({{snippet:name}}) →
  processConditionals({{#if flag}}...{{/if}}) → interpolateVariables({var})

与 BaseAgent._load_prompt() 集成，提供片段复用和条件渲染能力。
"""

import os
import re
import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_BASE = os.path.join(
    os.path.dirname(__file__), "..", "..", "prompts"
)


def _resolve_path(relative_path: str) -> str:
    """将相对 prompts/ 的路径解析为绝对路径"""
    return os.path.normpath(os.path.join(_PROMPTS_BASE, relative_path))


def load_snippet(snippet_name: str) -> str:
    """
    加载一个 snippet 片段。
    从 prompts/snippets/{name}.yaml 读取并返回原始文本。
    """
    snippet_path = _resolve_path(f"snippets/{snippet_name}.yaml")
    try:
        with open(snippet_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content.strip()
    except FileNotFoundError:
        logger.warning(f"Snippet not found: {snippet_path}")
        return f"[snippet:{snippet_name} not found]"


def process_snippets(template: str) -> str:
    """
    处理模板中的 {{snippet:name}} 引用。
    将占位符替换为实际 snippet 内容。
    """
    pattern = r"\{\{snippet:([a-zA-Z][\w-]*)\}\}"

    def replacer(match: re.Match) -> str:
        name = match.group(1)
        return load_snippet(name)

    return re.sub(pattern, replacer, template)


def process_conditionals(
    template: str, conditions: dict[str, Any] | None = None
) -> str:
    """
    处理模板中的 {{#if condition}}...{{/if}} 条件块。
    当 conditions[condition] 为 truthy 时保留内容，否则删除。
    """
    if conditions is None:
        conditions = {}

    pattern = r"\{\{#if (\w+)\}\}([\s\S]*?)\{\{/if\}\}"

    def replacer(match: re.Match) -> str:
        cond_name = match.group(1)
        content = match.group(2)
        return content if conditions.get(cond_name) else ""

    return re.sub(pattern, replacer, template)


def interpolate_variables(
    template: str, variables: dict[str, Any] | None = None
) -> str:
    """
    替换模板中的 {variable} 占位符。
    仅替换已知变量，未知的保留原样。
    """
    if variables is None:
        variables = {}

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return match.group(0)
        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return re.sub(r"\{(\w+)}", replacer, template)


def load_prompt_file(
    agent_name: str, filename: str = "system.yaml", key: str = "system"
) -> str:
    """
    加载 agent 的 prompt 文件并处理 snippet 引用。
    返回处理后的原始模板文本（变量尚未替换）。
    """
    prompt_path = _resolve_path(f"{agent_name}/{filename}")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        raw = data.get(key, "")
        return process_snippets(raw)
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ""


def build_prompt(
    agent_name: str,
    filename: str = "system.yaml",
    variables: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    key: str = "system",
) -> str:
    """
    完整的 prompt 构建流水线（借鉴 OpenMAIC buildPrompt）。

    处理顺序：
      1. 加载 YAML 文件
      2. 替换 {{snippet:name}} → snippet 内容
      3. 处理 {{#if flag}}...{{/if}} 条件块
      4. 替换 {variable} 变量

    返回可直接用于 LLM 调用的完整 prompt 文本。
    """
    template = load_prompt_file(agent_name, filename, key=key)
    template = process_conditionals(template, conditions)
    template = interpolate_variables(template, variables)
    return template
