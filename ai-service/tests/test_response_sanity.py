"""ResponseSanityCheck 测试（对话底座救援 · Task 8）。

只做高置信机械检查：空、重复、截断、内部提示泄露、语言明显冲突。
最多以相同 BuiltContext 重试一次；再失败返回可恢复错误与脱敏 error_code。
检查器不得改写正常回答，也不承担"事实绝对正确"的判定。
"""
import pytest

from app.services.response_sanity import (
    SanityVerdict,
    check_response,
    run_with_sanity_check,
)


# ═══════════════════════════════════════════════════════════════
# 计划规定的失败测试用例
# ═══════════════════════════════════════════════════════════════

class TestPlannedCases:
    def test_empty_string_is_retry_once(self):
        for text in ("", "   ", "\n\t "):
            r = check_response(text, "什么是进程？")
            assert r.verdict is SanityVerdict.RETRY_ONCE
            assert r.reason == "empty"

    def test_heavy_repetition_is_retry_once(self):
        text = "这是一个测试片段。" * 20
        r = check_response(text, "举个例子")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "heavy_repetition"

    def test_json_with_internal_prompt_fields_is_user_safe_error(self):
        text = (
            '{"system_prompt": "你是学习助手", "student_profile": {"level": 3},'
            ' "messages_history": [], "response": "进程是资源分配的基本单位"}'
        )
        r = check_response(text, "什么是进程？")
        assert r.verdict is SanityVerdict.USER_SAFE_ERROR
        assert r.reason == "prompt_leak"
        assert r.error_code

    def test_normal_chinese_answer_is_accepted_verbatim(self):
        text = (
            "进程是操作系统进行资源分配的基本单位。"
            "它拥有独立的地址空间，线程则共享所属进程的资源。"
            "你可以把进程想象成一家工厂，线程就是厂里的工人。"
        )
        r = check_response(text, "什么是进程？")
        assert r.verdict is SanityVerdict.ACCEPT
        assert r.error_code is None
        # 检查器不得改写正常回答
        assert r.text == text


# ═══════════════════════════════════════════════════════════════
# 其余机械检查
# ═══════════════════════════════════════════════════════════════

class TestMechanicalChecks:
    def test_truncated_code_fence_is_retry_once(self):
        text = "下面是用 Python 实现的快速排序：\n```python\ndef quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[0]"
        r = check_response(text, "用Python写一个快速排序")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "truncated"

    def test_mid_sentence_comma_ending_is_truncated(self):
        # 悬空连接标点：句子明显没说完（保守判定，见模块 docstring）
        text = "进程拥有独立的地址空间，而线程共享所属进程的资源，"
        r = check_response(text, "进程和线程的区别")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "truncated"

    def test_list_ending_without_period_not_truncated(self):
        # 无句号结尾的正常回答不得误伤
        text = "学习三步走：\n1. 先看概念\n2. 再做例题\n3. 最后自己推导一遍"
        r = check_response(text, "怎么学线性代数？")
        assert r.verdict is SanityVerdict.ACCEPT

    def test_language_mismatch_is_retry_once(self):
        text = (
            "A process is the basic unit of resource allocation in an operating "
            "system. It owns an isolated address space, while threads share the "
            "resources of their parent process and communicate more cheaply."
        )
        r = check_response(text, "什么是进程？")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "language_mismatch"


# ═══════════════════════════════════════════════════════════════
# 语言一致性检查的豁免：用户显式指定输出语言时不得判为不一致
#
# 线上回归（会话 75「写一篇 what matters to you」）：用户要求
# "输出不要中文，直接纯英文"，模型正确输出纯英文，却被 language_mismatch
# 判为异常；由于重试上下文完全相同，两轮必然同为英文，正文被整体丢弃，
# 表现为该问题 100% 答不出来。
# ═══════════════════════════════════════════════════════════════

ENGLISH_ESSAY = (
    "What Matters to Me\n\n"
    "When asked what matters most to me, the answer comes easily: the people who "
    "stand beside me and the chance to keep growing. In a world that often measures "
    "success by grades and titles, I have learned that what truly matters is "
    "connection and purpose. Family and friends shape who we are, and personal "
    "growth gives life meaning. It is not the destination but the journey that counts."
)


class TestExplicitLanguageOverride:
    """用户明确要求外语输出时，全外文回答属于正确履约。"""

    @pytest.mark.parametrize(
        "request_message",
        [
            # 线上真实触发语句
            "下面生成一篇纯六级的作文，就是针对上面这个，输出不要中文，直接纯英文。",
            "用英文回答这个问题",
            "请以英文写一篇关于环保的作文",
            "翻译成英文",
            "帮我写一段英文自我介绍",
            "回答不要用中文",
            "纯英文输出",
            "english only please",
            "translate into English",
            "no chinese, just english",
        ],
    )
    def test_english_answer_accepted_when_language_requested(self, request_message):
        r = check_response(ENGLISH_ESSAY, request_message)
        assert r.verdict is SanityVerdict.ACCEPT, (
            f"用户已指定输出语言，纯英文回答不应被判为异常：{request_message!r}"
        )
        # 检查器不得改写正文
        assert r.text == ENGLISH_ESSAY

    def test_override_survives_retry_orchestration(self):
        """端到端复现：修复前该请求两轮重试后必然返回 USER_SAFE_ERROR。"""
        import asyncio

        async def generate(_context):
            return ENGLISH_ESSAY

        outcome = asyncio.run(
            run_with_sanity_check(
                generate,
                {"q": 1},
                request_message="下面生成一篇纯六级的作文，输出不要中文，直接纯英文。",
                max_attempts=2,
            )
        )
        assert outcome.verdict is SanityVerdict.ACCEPT
        assert outcome.text == ENGLISH_ESSAY
        assert outcome.attempts == 1

    def test_chinese_answer_also_fine_when_override_present(self):
        """豁免是"不检查"，不是"要求英文"：要求英文但答了中文也不由本检查拦截。"""
        text = (
            "进程是操作系统进行资源分配的基本单位，它拥有独立的地址空间，"
            "线程则是 CPU 调度的基本单位，同一进程内的线程共享内存资源。"
        )
        r = check_response(text, "用英文回答：什么是进程？")
        assert r.verdict is SanityVerdict.ACCEPT

    # ── 反向防护：普通提问不得因豁免被放行 ──

    def test_mismatch_still_caught_without_override(self):
        """没有语言指令时，中文提问收到纯英文长篇仍应拦截。"""
        r = check_response(ENGLISH_ESSAY, "什么是进程？请解释一下")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "language_mismatch"

    def test_mentioning_english_term_is_not_an_override(self):
        """中文提问里顺带提到英文术语，不构成换语言要求。"""
        r = check_response(ENGLISH_ESSAY, "请解释一下 Python 的 GIL 机制")
        assert r.verdict is SanityVerdict.RETRY_ONCE
        assert r.reason == "language_mismatch"

    def test_chinese_answer_with_english_words_accepted(self):
        """中英混排的正常回答不受任何影响。"""
        text = (
            "Python 的 GIL 是全局解释器锁（Global Interpreter Lock），"
            "它保证同一时刻只有一个线程执行 Python 字节码，"
            "因此多线程在 CPU 密集场景下无法真正并行。"
        )
        r = check_response(text, "请解释一下 Python 的 GIL 机制")
        assert r.verdict is SanityVerdict.ACCEPT


# ═══════════════════════════════════════════════════════════════
# 误伤防护：正常形态不得被拦截
# ═══════════════════════════════════════════════════════════════

class TestNoFalsePositives:
    def test_code_answer_with_balanced_fences_accepted(self):
        text = (
            "用 Python 可以这样反转字符串：\n"
            "```python\n"
            "def reverse(s: str) -> str:\n"
            "    return s[::-1]\n"
            "```\n"
            "切片步长为 -1 即可。"
        )
        r = check_response(text, "怎么反转字符串？")
        assert r.verdict is SanityVerdict.ACCEPT

    def test_benign_json_teaching_example_accepted(self):
        text = (
            'JSON 里表示一条配置可以这样写：{"name": "tcp", "port": 80,'
            ' "enabled": true}，注意键名用双引号。'
        )
        r = check_response(text, "JSON 的键名规则是什么？")
        assert r.verdict is SanityVerdict.ACCEPT

    def test_short_but_valid_answer_accepted(self):
        r = check_response("进程就是正在运行的程序实例。", "什么是进程？")
        assert r.verdict is SanityVerdict.ACCEPT

    def test_english_answer_to_english_question_accepted(self):
        text = (
            "A process is the basic unit of resource allocation in an operating "
            "system. It owns an isolated address space, while threads share the "
            "resources of their parent process."
        )
        r = check_response(text, "What is a process?")
        assert r.verdict is SanityVerdict.ACCEPT


# ═══════════════════════════════════════════════════════════════
# 重试编排：第一次失败重试一次，再失败返回可恢复错误
# ═══════════════════════════════════════════════════════════════

def _fake_generate(responses):
    calls = []

    async def generate(context):
        calls.append(dict(context))
        return responses[min(len(calls) - 1, len(responses) - 1)]

    generate.calls = calls
    return generate


class TestRetryOrchestration:
    @pytest.mark.asyncio
    async def test_retry_success_after_empty_first_attempt(self):
        gen = _fake_generate(["   ", "进程是资源分配的基本单位，它有独立地址空间。"])
        outcome = await run_with_sanity_check(gen, {"question": "什么是进程？"})
        assert outcome.verdict is SanityVerdict.ACCEPT
        assert outcome.text == "进程是资源分配的基本单位，它有独立地址空间。"
        assert outcome.attempts == 2
        assert outcome.failure_reasons == ["empty"]
        assert outcome.error_code is None
        # 相同 BuiltContext 重试
        assert gen.calls[0] == gen.calls[1] == {"question": "什么是进程？"}

    @pytest.mark.asyncio
    async def test_two_consecutive_failures_yield_recoverable_error(self):
        gen = _fake_generate(["   ", "   "])
        outcome = await run_with_sanity_check(gen, {"question": "什么是进程？"})
        # 绝不伪造 content：text 必须为 None，由调用方转成 SSE error
        assert outcome.text is None
        assert outcome.verdict is SanityVerdict.USER_SAFE_ERROR
        assert outcome.attempts == 2
        assert outcome.error_code == "EMPTY_RESPONSE"
        assert outcome.failure_reasons == ["empty", "empty"]

    @pytest.mark.asyncio
    async def test_leak_is_not_retried(self):
        gen = _fake_generate(['{"system_prompt": "内部提示", "response": "x"}'])
        outcome = await run_with_sanity_check(gen, {"question": "什么是进程？"})
        assert outcome.verdict is SanityVerdict.USER_SAFE_ERROR
        assert outcome.error_code == "PROMPT_LEAK"
        assert outcome.attempts == 1

    @pytest.mark.asyncio
    async def test_error_code_is_sanitized(self):
        gen = _fake_generate(["   ", "   "])
        outcome = await run_with_sanity_check(gen, {"question": "什么是进程？"})
        # 脱敏：error_code 不携带任何回答片段或内部细节
        assert isinstance(outcome.error_code, str)
        assert "进程" not in outcome.error_code
