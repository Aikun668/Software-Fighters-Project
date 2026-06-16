import asyncio
import os
import pytest
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.asyncio(loop_scope="function")


def pytest_addoption(parser):
    parser.addoption(
        "--real-llm",
        action="store_true",
        default=False,
        help="Run tests against real LLM instead of mock",
    )
    parser.addoption(
        "--use-real-llm",
        action="store_true",
        default=bool(os.environ.get("USE_REAL_LLM")),
        help="Run tests against real LLM (env: USE_REAL_LLM=1)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "real_llm: test requires real LLM call")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--real-llm") or config.getoption("--use-real-llm"):
        return
    skip_real_llm = pytest.mark.skip(reason="needs --real-llm flag or USE_REAL_LLM=1")
    for item in items:
        if "real_llm" in item.keywords:
            item.add_marker(skip_real_llm)

@pytest.fixture(autouse=True)
def mock_sleep():
    with patch("asyncio.sleep"):
        yield

@pytest.fixture
def student_profile():
    return {
        "knowledge_base": 50,
        "cognitive_style": "visual",
        "learning_goal": "掌握深度学习",
        "weak_points": ["数学基础", "Python"],
        "learning_pace": "moderate",
        "interest_direction": ["计算机视觉", "NLP"],
    }

@pytest.fixture
def messages():
    return [
        {"role": "user", "content": "我想学习机器学习"},
        {"role": "assistant", "content": "好的，我来了解一下你的基础。"},
        {"role": "user", "content": "我数学不太好，但对图像识别感兴趣"},
    ]

@pytest.fixture
def outline_sample():
    return {
        "intro": "Python是一种高级编程语言",
        "subsections": [
            {"heading": "变量与数据类型", "role": "core", "focus": "变量定义"},
            {"heading": "控制流", "role": "example", "focus": "if语句"},
        ],
        "key_takeaway": "掌握Python基础语法",
    }
