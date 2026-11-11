package com.university.learning.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * P1 回归：调整规则不能"看起来听懂了就动手"。
 * 否定句、复述历史用量不得改动计划；报卡点/改期限不得顺手拆分并覆盖断点；每日分钟数要拆全部受影响任务。
 */
class AdaptivePlanAdjustmentRulesTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private AdaptivePlanService service;

    @BeforeEach
    void setup() {
        JdbcTemplate jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        service = new AdaptivePlanService(jdbc, mapper);
    }

    private JsonNode body(String json) throws Exception {
        return mapper.readTree(json);
    }

    /** 一个 45 分钟任务 + 一个 15 分钟任务，每日 30 分钟。 */
    private ObjectNode create() throws Exception {
        return service.create(1L, body("{\"title\":\"数据库\",\"goal\":\"掌握事务\",\"dailyMinutes\":30,"
                + "\"modules\":[{\"title\":\"隔离级别\",\"tasks\":["
                + "{\"title\":\"幻读例子\",\"minutes\":45},{\"title\":\"总结\",\"minutes\":15}]}]}"));
    }

    private int totalMinutes(JsonNode plan) {
        int sum = 0;
        for (JsonNode m : plan.path("modules")) {
            for (JsonNode t : m.path("tasks")) {
                sum += t.path("minutes").asInt();
            }
        }
        return sum;
    }

    private ResponseStatusException rejected(String planId, String message) {
        return assertThrows(ResponseStatusException.class,
                () -> service.propose(1L, planId, body("{\"version\":1,\"message\":\"" + message + "\"}")));
    }

    @Test
    void negatedDeferDoesNotTouchThePlan() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        ResponseStatusException error = rejected(planId, "不延期");
        assertTrue(String.valueOf(error.getReason()).contains("否定指令"), "实际：" + error.getReason());

        JsonNode stored = service.get(1L, planId);
        assertEquals(1, stored.path("version").asInt(), "否定指令不得改动计划");
        assertEquals("pending", stored.path("modules").get(0).path("tasks").get(0).path("status").asText());
    }

    @Test
    void negatedBlockerReportIsNotABlocker() throws Exception {
        ObjectNode plan = create();
        assertTrue(String.valueOf(rejected(plan.path("id").asText(), "没有卡住").getReason()).contains("否定指令"));
        assertEquals("pending",
                service.get(1L, plan.path("id").asText()).path("modules").get(0).path("tasks").get(0).path("status").asText());
    }

    @Test
    void pastUsageSentenceDoesNotBecomeABudget() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        // "某一天我用了 20 分钟" 是复述已发生的用量，不是"每天改成 20 分钟"
        rejected(planId, "某一天我用了 20 分钟");

        JsonNode stored = service.get(1L, planId);
        assertEquals(30, stored.path("dailyMinutes").asInt(), "复述历史用量不得改每日预算");
        assertEquals(1, stored.path("version").asInt());
    }

    @Test
    void negationOnlyAppliesToTheIntentItNegates() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        JsonNode proposal = service.propose(1L, planId,
                body("{\"version\":1,\"message\":\"不延期，但每天改成20分钟\"}"));

        assertEquals(20, proposal.path("proposedPlan").path("dailyMinutes").asInt());
        for (JsonNode task : proposal.path("proposedPlan").path("modules").get(0).path("tasks")) {
            assertFalse("deferred".equals(task.path("status").asText()), "被否定的延期不能生效");
        }
    }

    @Test
    void blockerReportDoesNotSplitOrOverwriteCheckpoint() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        JsonNode proposal = service.propose(1L, planId,
                body("{\"version\":1,\"message\":\"幻读这个例子的思路我卡住了\"}"));

        JsonNode tasks = proposal.path("proposedPlan").path("modules").get(0).path("tasks");
        assertEquals(2, tasks.size(), "报卡点不应顺手把超长任务拆开");
        JsonNode first = tasks.get(0);
        assertEquals("blocked", first.path("status").asText());
        assertEquals(45, first.path("minutes").asInt(), "报卡点不得覆盖任务本身的分钟数");
        assertTrue(first.path("checkpoint").asText().contains("卡住"), "断点正文必须被记录");

        assertEquals(1, proposal.path("changes").size(), "只应有卡点这一条变更");
        assertEquals("checkpoint", proposal.path("changes").get(0).path("kind").asText());
        assertEquals(45, proposal.path("changes").get(0).path("before").path("minutes").asInt());
        assertTrue(proposal.path("changes").get(0).path("after").path("checkpoint").asText().contains("卡住"),
                "确认稿里的 after 必须带断点正文");
    }

    @Test
    void deadlineOnlyChangeDoesNotSplitTasks() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        JsonNode proposal = service.propose(1L, planId,
                body("{\"version\":1,\"message\":\"把截止日期往后放一点\",\"deadline\":\"2099-12-31\"}"));

        assertEquals(2, proposal.path("proposedPlan").path("modules").get(0).path("tasks").size(),
                "只改截止日期不应重排任务");
        assertEquals(45, proposal.path("proposedPlan").path("modules").get(0).path("tasks").get(0).path("minutes").asInt());
        assertEquals("deadline", proposal.path("changes").get(0).path("kind").asText());
    }

    @Test
    void deferAndBlockerInOneSentenceRequireAnExplicitChoice() throws Exception {
        ObjectNode plan = create();
        String planId = plan.path("id").asText();

        ResponseStatusException error = rejected(planId, "这个任务卡住了，顺便延期吧");
        assertTrue(String.valueOf(error.getReason()).contains("分开"), "实际：" + error.getReason());
        assertEquals(1, service.get(1L, planId).path("version").asInt());
    }

    @Test
    void budgetChangeSplitsEveryOverBudgetTaskAndConservesMinutes() throws Exception {
        ObjectNode plan = service.create(1L, body("{\"title\":\"复习\",\"goal\":\"数据库\",\"dailyMinutes\":30,"
                + "\"modules\":[{\"title\":\"事务\",\"tasks\":["
                + "{\"title\":\"任务一\",\"minutes\":45},{\"title\":\"任务二\",\"minutes\":60},"
                + "{\"title\":\"任务三\",\"minutes\":50},{\"title\":\"任务四\",\"minutes\":40},"
                + "{\"title\":\"任务五\",\"minutes\":10}]}]}"));
        String planId = plan.path("id").asText();

        JsonNode proposal = service.propose(1L, planId, body("{\"version\":1,\"message\":\"每天20分钟\"}"));
        JsonNode tasks = proposal.path("proposedPlan").path("modules").get(0).path("tasks");

        int splits = 0;
        for (JsonNode change : proposal.path("changes")) {
            if ("split".equals(change.path("kind").asText())) {
                splits++;
            }
        }
        assertEquals(4, splits, "所有超预算任务都要拆（45/60/50/40 四个），不能只拆前 3 个");
        for (JsonNode task : tasks) {
            assertTrue(task.path("minutes").asInt() <= 20,
                    "拆完后每个任务都不能超过每日预算，实际 " + task.path("minutes").asInt());
        }
        assertEquals(205, totalMinutes(proposal.path("proposedPlan")), "拆分必须守恒总分钟数");
    }

    @Test
    void confirmationSheetHasNoFillerKeeps() throws Exception {
        ObjectNode plan = create();
        JsonNode proposal = service.propose(1L, plan.path("id").asText(),
                body("{\"version\":1,\"message\":\"每天20分钟\"}"));

        for (JsonNode change : proposal.path("changes")) {
            assertFalse("keep".equals(change.path("kind").asText()), "确认稿不应夹满「保留」行");
        }
        boolean hasBudget = false;
        for (JsonNode change : proposal.path("changes")) {
            if ("budget".equals(change.path("kind").asText())) {
                hasBudget = true;
                assertEquals(30, change.path("before").asInt());
                assertEquals(20, change.path("after").asInt());
            }
        }
        assertTrue(hasBudget, "确认稿必须显示每日时间的变化");
    }
}
