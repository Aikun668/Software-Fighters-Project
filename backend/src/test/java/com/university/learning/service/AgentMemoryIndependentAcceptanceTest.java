package com.university.learning.service;

import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Independent adversarial probes frozen before implementation acceptance. Synthetic H2 only. */
class AgentMemoryIndependentAcceptanceTest {
    private JdbcTemplate jdbc;
    private AgentMemoryService memory;
    @BeforeEach void setup() {
        jdbc = new JdbcTemplate(new DriverManagerDataSource(
            "jdbc:h2:mem:independent_memory_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        memory = new AgentMemoryService(jdbc, true);
    }
    @SuppressWarnings("unchecked")
    private List<Map<String,Object>> facts(Map<String,Object> result) {
        return (List<Map<String,Object>>) result.get("facts");
    }
    private Map<String,Object> fact(Map<String,Object> result, String key) {
        return facts(result).stream().filter(f -> key.equals(f.get("key"))).findFirst().orElseThrow();
    }

    @Test void weeklyConstraintRetainsItsUnitInsteadOfTurningIntoDailyBudget() {
        Map<String,Object> result = memory.observe(1L, 10L, 100L, "我每周只能抽出三小时复习。");
        assertTrue(fact(result,"time_budget").get("value").toString().contains("三小时"));
        String contextual = fact(result,"time_budget").toString();
        assertTrue(contextual.contains("每周"), "Weekly qualifier must remain attributable");
        assertFalse(fact(result,"time_budget").get("label").toString().contains("每天"));
    }

    @Test void naturalCorrectionDistinguishesNewGoalFromExplicitlyNegatedOldGoal() {
        memory.observe(1L,10L,100L,"我这学期的目标是通过数据库考试。");
        Map<String,Object> result = memory.observe(1L,10L,110L,
            "不对，我现在的目标是通过操作系统考试，不是数据库考试。");
        String value = fact(result,"learning_goal").get("value").toString();
        assertTrue(value.contains("操作系统"));
        assertFalse(value.contains("数据库"), "Negated old goal must not be stored as current value");
        List<Map<String,Object>> old = List.of(
            Map.of("id",100L,"role","user","content","我这学期的目标是通过数据库考试。"),
            Map.of("id",101L,"role","assistant","content","你的目标是通过数据库考试。"));
        assertTrue(memory.filterHistory(old,result).isEmpty(), "Neither user source nor assistant paraphrase may revive the superseded goal");
    }

    @Test void sameConversationForgetSurvivesReopenAndOldAssistantParaphrase() {
        memory.observe(1L,10L,100L,"我的学习目标是通过数据库考试。");
        memory.observe(1L,10L,110L,"忘记我的学习目标");
        AgentMemoryService fresh = new AgentMemoryService(jdbc,true);
        Map<String,Object> state = fresh.observe(1L,10L,120L,"我原来想通过什么考试？");
        assertTrue(facts(state).isEmpty());
        assertFalse(state.toString().contains("数据库考试"));
        List<Map<String,Object>> old = List.of(
            Map.of("id",100L,"role","user","content","我的学习目标是通过数据库考试。"),
            Map.of("id",101L,"role","assistant","content","你的目标是通过数据库考试。"));
        assertTrue(fresh.filterHistory(old,state).isEmpty());
    }

    @Test void forgettingOneUsersFactDoesNotAffectSameConversationNumberForAnotherUser() {
        memory.observe(1L,10L,100L,"记住：学习目标=通过数据库考试");
        memory.observe(2L,10L,101L,"记住：学习目标=通过操作系统考试");
        memory.observe(1L,20L,200L,"忘记我的学习目标");
        assertTrue(facts(memory.observe(1L,10L,201L,"查看记忆")).isEmpty());
        assertEquals("通过操作系统考试",fact(memory.observe(2L,30L,202L,"查看记忆"),"learning_goal").get("value"));
    }

    @Test void hypotheticalQuotedAndThirdPartyGoalsAreNotMyLearningGoals() {
        for(String input: List.of(
            "如果我的目标是通过数据库考试，该怎么安排？",
            "例句是：我的学习目标是通过数据库考试。",
            "小王说：我的学习目标是通过数据库考试。",
            "我替朋友问：我的学习目标是通过数据库考试。",
            "请翻译：我的学习目标是通过数据库考试。")) {
            assertTrue(facts(memory.observe(1L,10L,100L,input)).isEmpty(), input);
        }
    }

    @Test void rememberWithQuestionDoesNotConfirmAndSilentlyConsumeQuestion() {
        Map<String,Object> state=memory.observe(1L,10L,100L,
            "记住：学习目标=通过数据库考试。然后解释什么是事务隔离级别？");
        String reply=Objects.toString(state.get("command_reply"),"");
        // A pure command reply is insufficient unless the ordinary question is explicitly carried onward.
        assertTrue(reply.isBlank() || state.containsKey("remaining_message") || state.containsKey("continue_message"),
            "Mixed remember + ordinary question cannot take the pure-command short circuit");
        for(Map<String,Object> f:facts(state)) {
            assertFalse(f.get("value").toString().contains("解释什么"), "A question is not a learning fact");
        }
    }

    @Test void syntheticCredentialVariantsNeverBecomeInspectableFacts() {
        for(String input:List.of(
            "记住：备注=Bearer synthetic-token-not-real-0123456789",
            // Cloud-transfer redaction removed the original credential-shaped fixture. Use a synthetic shape, never a real key.
            "记住：备注=" + "sk-" + "synthetic-not-a-real-key-0123456789",
            "我的学习目标是保存 password=not-a-real-password",
            "请记住：备注=api_key: synthetic-abcdef0123456789")) {
            Map<String,Object> state=memory.observe(1L,10L,100L,input);
            assertTrue(facts(state).isEmpty(), "Credential-shaped test value entered facts");
            assertFalse(Objects.toString(state.get("command_reply"),"").contains("已记住"));
        }
    }
}
