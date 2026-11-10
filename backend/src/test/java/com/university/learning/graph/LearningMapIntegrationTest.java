package com.university.learning.graph;
import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import org.springframework.http.MediaType;

class LearningMapIntegrationTest {
    final LearningMapIntegrationFixture fixture=new LearningMapIntegrationFixture();
    final ObjectMapper json=new ObjectMapper();
    JsonNode map(String user) throws Exception { return json.readTree(fixture.mvc.perform(get("/api/learning-map").header("X-Test-User",user)).andReturn().getResponse().getContentAsString()).get("data"); }
    @Test void realSqlSourcesProduceDistinctTrajectoryAndPendingBridge() throws Exception {
        JsonNode data=map("1"); assertEquals(4,data.get("nodes").size());
        assertEquals(4,data.get("events").size()); assertEquals(2,data.get("suggestions").size());
        assertEquals("pending",data.get("suggestions").get(0).get("status").asText());
        assertEquals(0,data.get("edges").size());
        assertTrue(data.toString().contains("practice_self_report"));
        assertFalse(data.toString().contains("秘密主题"));
    }
    @Test void educationalQuestionAndGoalCommandsKeepSourceWithoutInventingNode() throws Exception {
        fixture.add(10,1,"记住：学习目标=掌握机器学习");
        fixture.add(11,1,"为什么训练损失下降但验证变差？");
        JsonNode data=map("1");
        assertEquals(6,data.get("events").size());
        assertTrue(data.get("events").toString().contains("训练损失"));
        assertEquals(4,data.get("nodes").size());
    }
    @Test void invalidOrForgottenSuggestionCannotBeDecided() throws Exception {
        assertEquals(404,fixture.mvc.perform(post("/api/learning-map/suggestions/fake/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
        String id=map("1").get("suggestions").get(0).get("id").asText();
        fixture.jdbc.update("DELETE FROM messages WHERE conversation_id=1");
        assertEquals(404,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
    }
    @Test void practiceCompletionQuestionsNeverBecomeCompletionClaims() throws Exception {
        fixture.add(10,1,"我完成了概率论练习吗？");
        fixture.add(11,1,"我做完这道题了吗？");
        fixture.add(12,1,"如果我完成了概率论练习");
        fixture.add(13,1,"我的学习目标是什么？");
        JsonNode events=map("1").get("events");
        for(JsonNode event:events) {
            if(event.get("id").asText().startsWith("message-10-") || event.get("id").asText().startsWith("message-11-"))
                assertEquals("question",event.get("type").asText());
            if(event.get("id").asText().startsWith("message-12-"))
                assertNotEquals("practice_self_report",event.get("type").asText());
        }
        assertTrue(events.toString().contains("message-10-question"));
        assertTrue(events.toString().contains("message-11-question"));
        assertTrue(events.toString().contains("message-13-question"));
        assertFalse(events.toString().contains("message-13-goal"));
    }
    @Test void questionAssociationDoesNotDependOnConversationTraversalOrder() throws Exception {
        fixture.jdbc.update("INSERT INTO conversations VALUES(3,1,'较新提问会话',TIMESTAMP '2030-01-01 00:00:00')");
        fixture.add(10,3,"线性代数难吗？");
        String newerFirst=map("1").get("events").toString();
        assertTrue(newerFirst.contains("message-10-question"));
        fixture.jdbc.update("UPDATE conversations SET updated_at=TIMESTAMP '2000-01-01 00:00:00' WHERE id=3");
        assertEquals(newerFirst,map("1").get("events").toString());
    }
    @Test void decisionsPersistByOwnerAndNeverBecomeDependency() throws Exception {
        String id=map("1").get("suggestions").get(0).get("id").asText();
        assertEquals(200,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
        assertEquals("accepted",new com.university.learning.service.LearningMapDecisionService(fixture.jdbc).read(1L).get(id));
        assertEquals("user_confirmed",map("1").get("edges").get(0).get("relation").asText());
        assertEquals(404,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","2").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
        assertEquals(400,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"bad\"}")).andReturn().getResponse().getStatus());
        assertEquals(200,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"rejected\"}")).andReturn().getResponse().getStatus());
        assertEquals(0,map("1").get("edges").size());
    }
    @Test void persistenceFailureIs503NotPretendSuccess() throws Exception {
        String id=map("1").get("suggestions").get(0).get("id").asText();
        fixture.jdbc.execute("DROP TABLE learning_map_decision");
        assertEquals(503,fixture.mvc.perform(post("/api/learning-map/suggestions/"+id+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
    }
    @Test void continuationRevalidatesForgottenSourcesAndRequiresIdentity() throws Exception {
        String id=map("1").get("nodes").get(0).get("id").asText();
        String suggestionId=map("1").get("suggestions").get(0).get("id").asText();
        var response=fixture.mvc.perform(get("/api/learning-map/nodes/"+id+"/continuation").header("X-Test-User","1")).andReturn().getResponse();
        String draft=json.readTree(response.getContentAsString()).get("data").get("draft").asText();
        assertTrue(draft.contains("消息")); assertTrue(draft.contains("历史资料")); assertTrue(draft.length()<2000);
        assertEquals(401,fixture.mvc.perform(get("/api/learning-map")).andReturn().getResponse().getStatus());
        fixture.add(20,1,"忘记：当前主题");
        var forgotten=fixture.memory.observe(1L,1L,20L,"忘记：当前主题");
        assertTrue(forgotten.get("command_reply").toString().contains("忘记"));
        assertEquals(0,map("1").get("nodes").size());
        assertEquals(0,map("1").get("suggestions").size());
        assertEquals(404,fixture.mvc.perform(post("/api/learning-map/suggestions/"+suggestionId+"/decision").header("X-Test-User","1").contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}")).andReturn().getResponse().getStatus());
        assertEquals(404,fixture.mvc.perform(get("/api/learning-map/nodes/"+id+"/continuation").header("X-Test-User","1")).andReturn().getResponse().getStatus());
    }
}
