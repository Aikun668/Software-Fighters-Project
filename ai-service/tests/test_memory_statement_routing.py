"""Regression for real conv162: an observed progress statement generated a plan."""
import pytest
from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.services.intent_extractor import IntentExtractor,IntentResult,MultiIntentResult

class SemanticPlan:
    calls=0
    async def extract_multi(self,message,max_intents=3,clarity_threshold=0.5):
        self.calls+=1
        return MultiIntentResult(intents=[IntentResult(intent='learning_path',confidence=0.99)],
            is_clear=True,raw_message=message)


def memory(message,key='progress'):
    return {'_agent_memory':{'schema_version':1,'user_id':1,'conversation_id':162,'facts':[
        {'key':key,'label':'学习进度','value':'已学完索引，接下来学事务','scope':'session',
         'source_message_id':399,'source_conversation_id':162,'source_quote':message,'updated_at':'2026-11-09T11:26:09Z'}]}}


def center():
    semantic=SemanticPlan()
    return ChatCenter(router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        use_mock_llm=True,t4a_enabled=True,semantic_extractor=semantic),semantic


@pytest.mark.asyncio
@pytest.mark.parametrize('message,key',[
    ('我已经学完索引，接下来学事务。','progress'),
    ('我这学期的目标是通过数据库考试。','learning_goal'),
    ('我最近在复习事务隔离级别。','current_topic'),
    ('我还是分不清可重复读和幻读。','blocker'),
    ('我每周只能抽出三小时复习。','time_budget')])
async def test_observed_learning_statement_cannot_be_upgraded_to_unrequested_plan(message,key):
    c,semantic=center()
    plan=await c.route(message,student_profile=memory(message,key))
    assert [task.mode for task in plan.tasks]==['auto']
    assert [task.intent for task in plan.tasks]==['tutor_question']
    assert semantic.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,message',[
    ('auto','我已经学完索引，接下来学事务，请帮我制定学习计划。'),
    ('plan','我已经学完索引，接下来学事务。')])
async def test_explicit_plan_request_and_button_keep_plan_capability(mode,message):
    c,_=center()
    plan=await c.route(message,mode=mode,student_profile=memory(message))
    assert [task.mode for task in plan.tasks]==['plan']


@pytest.mark.asyncio
async def test_unrelated_or_missing_memory_does_not_change_existing_route():
    message='我已经学完索引，接下来学事务。'
    for profile in ({},memory('我已学完别的内容。')):
        c,semantic=center()
        plan=await c.route(message,student_profile=profile)
        assert [task.mode for task in plan.tasks]==['plan']
        assert semantic.calls==1

@pytest.mark.asyncio
async def test_statement_with_reply_length_request_still_does_not_create_plan():
    message='我已经学完索引，接下来学事务。请只用一句话回复。'
    c,semantic=center()
    plan=await c.route(message,student_profile=memory(message))
    assert [task.intent for task in plan.tasks]==['tutor_question']
    assert semantic.calls==0

@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,expected_mode',[
    ('给我一句简短回复。','auto'),('麻烦简短回应即可。','auto'),
    ('写一份七天复习清单。','plan'),('设计一个练习项目。','plan')])
async def test_style_requests_are_not_artifacts_but_real_deliverables_keep_semantic_route(suffix,expected_mode):
    message='我已经学完索引，接下来学事务。'+suffix
    c,semantic=center()
    plan=await c.route(message,student_profile=memory(message))
    assert [task.mode for task in plan.tasks]==[expected_mode]
    assert semantic.calls==(0 if expected_mode=='auto' else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("message",["我最近在学动态规划。", "我正在学习搜索算法。"])
async def test_learning_subject_words_are_not_artifact_requests(message):
    c, semantic = center()
    plan = await c.route(message, student_profile=memory(message))
    assert [p.mode for p in plan.tasks] == ["auto"]
    assert semantic.calls == 0
