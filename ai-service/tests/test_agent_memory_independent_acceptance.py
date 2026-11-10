"""Independent, offline-only adversarial memory-consumption acceptance probes."""
import pytest
from unittest.mock import AsyncMock
from app.services import agent_memory


def fact(**kw):
    result=dict(key='learning_goal',label='学习目标',value='通过数据库考试',scope='session',
        source_message_id=100,source_conversation_id=10,
        source_quote='我的学习目标是通过数据库考试',updated_at='2026-11-09T01:00:00Z')
    result.update(kw)
    return result


def envelope(**kw):
    result=dict(schema_version=1,user_id=1,conversation_id=10,facts=[],suppressed_message_ids=[])
    result.update(kw)
    return result


def validate(raw):
    return agent_memory.validate_memory(raw,user_id=1,conversation_id=10)


def test_java_global_wire_scope_survives_python_validation():
    actual_java_snapshot=envelope(facts=[fact(scope='global',source_conversation_id=20)])
    accepted=validate(actual_java_snapshot)
    assert len(accepted['facts'])==1
    assert accepted['facts'][0]['source_conversation_id']==20


@pytest.mark.parametrize('bad',[fact(key=[]),fact(source_message_id='1'*5000),fact(source_conversation_id='1'*5000)])
def test_malformed_source_shape_is_rejected_without_raising(bad):
    accepted=validate(envelope(facts=[bad]))
    assert accepted.get('facts',[])==[]


def test_sensitive_command_reply_cannot_bypass_fact_filter():
    accepted=validate(envelope(command_reply='已记住：密码=synthetic-only-not-real'))
    assert 'synthetic-only-not-real' not in accepted.get('command_reply','')
    assert not accepted.get('command_reply','').startswith('已记住')


def test_sensitive_turn_drops_benign_assistant_echo_too():
    history=[dict(id=1,role='user',content='我的密码是synthetic-crow'),
        dict(id=2,role='assistant',content='我记下了synthetic-crow'),
        dict(id=3,role='user',content='解释二分搜索'),dict(id=4,role='assistant',content='二分搜索每次折半')]
    filtered=agent_memory.filter_history(history,validate(envelope()))
    assert [m['id'] for m in filtered]==[3,4]


def test_weekly_budget_is_not_relabelled_daily_in_python():
    accepted=validate(envelope(facts=[fact(key='time_budget',label='每周学习时间',value='每周三小时',
        source_quote='我每周只能抽出三小时复习。')]))
    assert accepted['facts']
    assert '每天' not in accepted['facts'][0]['label']


@pytest.mark.asyncio
async def test_command_reply_cannot_suppress_unrelated_normal_question(monkeypatch):
    from app.centers.chat_center import ChatCenter
    center=ChatCenter(use_mock_llm=True)
    route=AsyncMock(side_effect=RuntimeError('normal-route-called'))
    monkeypatch.setattr(center,'route',route)
    with pytest.raises(RuntimeError,match='normal-route-called'):
        [e async for e in center.stream_chat(message='解释二分搜索',user_id=1,conversation_id=10,
            student_profile={'_agent_memory':envelope(command_reply='已记住学习目标。')})]
    assert route.call_args.kwargs['message']=='解释二分搜索'



def test_persisted_interrupted_turn_is_not_deleted_when_current_text_repeats():
    from app.services.context_builder import ContextBuilder
    text='再讲一下递归'
    built=ContextBuilder().build(system='学习助手',current_message=text,
        history=[dict(id=100,role='user',content=text)],agent_memory=validate(envelope()))
    result=built.messages()
    assert len(result)==2
    assert result[0].get('id')==100
    assert result[-1]['role']=='user' and result[-1]['content']==text


@pytest.mark.parametrize('message',[
    '显示我的学习记忆', '请查看学习记忆', '列出我的记忆',
    '修改：学习目标=通过软考', '删除：学习目标',
    '不对，我现在的目标是通过操作系统考试，不是数据库考试。'])
def test_java_supported_pure_management_sentence_uses_deterministic_result(message):
    assert agent_memory.is_management_request(message)
