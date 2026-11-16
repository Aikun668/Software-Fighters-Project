package com.university.learning.utils;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.university.learning.client.PythonClient;
import com.university.learning.common.GlobalExceptionHandler;
import com.university.learning.controller.AdaptivePlanController;
import com.university.learning.controller.ConversationController;
import com.university.learning.controller.LearningMapController;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.service.AdaptivePlanService;
import com.university.learning.service.AgentMemoryService;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IFileInfoService;
import com.university.learning.service.IMessageService;
import com.university.learning.service.LearningMapDecisionService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * Requests go through RefreshTokenInterceptor and then LoginInterceptor, in the
 * same order as {@code MvcConfig}. {@code learning.auth.required} is false, matching
 * the repository default. Identity is a Redis login token, not {@code UserHolder.saveUser}
 * and not {@code X-Test-User}.
 */
class LoginInterceptorIdentityTest {
    private static final String USER_ONE_SENTENCE = "我想学习线性代数";
    private static final String USER_SEVEN_SENTENCE = "我想学习图论";
    private static final String SECRET_SENTENCE = "我想学习仅属于一号的原句";
    private static final String USER_ONE_PLAN = "仅一号的自适应计划";
    private static final String USER_SEVEN_PLAN = "七号的自适应计划";
    private static final String TOKEN_ONE = "Bearer tok-1";
    private static final String TOKEN_SEVEN = "Bearer tok-7";

    private final ObjectMapper json = new ObjectMapper();
    private JdbcTemplate jdbc;
    private MockMvc mvc;
    private LoginInterceptor login;
    private StringRedisTemplate redis;
    private LearningMapController map;
    private AdaptivePlanController plans;
    private ConversationController conversations;
    private IConversationService conversationWrites;

    @BeforeEach
    void setUp() throws Exception {
        UserHolder.removeUser();
        jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:auth_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE conversations(id BIGINT PRIMARY KEY,user_id BIGINT,title VARCHAR(200),updated_at TIMESTAMP)");
        jdbc.execute("CREATE TABLE messages(id BIGINT PRIMARY KEY,conversation_id BIGINT,role VARCHAR(20),content VARCHAR(9000),created_at TIMESTAMP)");
        jdbc.update("INSERT INTO conversations VALUES(11,1,'一号',CURRENT_TIMESTAMP),(77,7,'七号',CURRENT_TIMESTAMP)");
        addMessage(101, 11, USER_ONE_SENTENCE);
        addMessage(102, 11, "我想学习计算机图形学");
        addMessage(701, 77, USER_SEVEN_SENTENCE);
        addMessage(702, 77, "我想学习社交网络");

        IConversationService ownedConversations = proxy(IConversationService.class, (method, args) -> {
            if (!"listByUserId".equals(method.getName())) throw new UnsupportedOperationException(method.getName());
            return jdbc.query("SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
                    (rs, n) -> new Conversation().setId(rs.getLong("id")).setUserId(rs.getLong("user_id")).setTitle(rs.getString("title")),
                    args[0]);
        });
        IMessageService ownedMessages = proxy(IMessageService.class, (method, args) -> {
            if (!"listRecentByConversationId".equals(method.getName())) throw new UnsupportedOperationException(method.getName());
            return jdbc.query("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
                    (rs, n) -> new Message().setId(rs.getLong("id")).setConversationId(rs.getLong("conversation_id"))
                            .setRole(rs.getString("role")).setContent(rs.getString("content"))
                            .setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime()),
                    args[0], args[1]);
        });
        map = new LearningMapController(ownedConversations, ownedMessages,
                new AgentMemoryService(jdbc, true), new LearningMapDecisionService(jdbc));
        AdaptivePlanService planService = new AdaptivePlanService(jdbc, json);
        planService.create(1, json.readTree(plan(USER_ONE_PLAN)));
        planService.create(7, json.readTree(plan(USER_SEVEN_PLAN)));
        plans = new AdaptivePlanController(planService);

        conversationWrites = mock(IConversationService.class);
        when(conversationWrites.getById(10L)).thenReturn(new Conversation().setId(10L).setUserId(1L));
        IMessageService storedSentences = mock(IMessageService.class);
        when(storedSentences.listByConversationId(10L)).thenReturn(List.of(
                new Message().setId(3L).setConversationId(10L).setRole("user").setContent(SECRET_SENTENCE)));
        conversations = new ConversationController(conversationWrites, storedSentences,
                mock(IFileInfoService.class), mock(PythonClient.class), new AgentMemoryService(null, false));

        redis = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        HashOperations<String, Object, Object> hashes = mock(HashOperations.class);
        when(redis.opsForHash()).thenReturn(hashes);
        when(hashes.entries(any())).thenAnswer(invocation -> {
            Object rawKey = invocation.getRawArguments()[0];
            String key = rawKey == null ? "" : rawKey.toString();
            if ("login:token:tok-1".equals(key)) return tokenUser("1", "learner-one");
            if ("login:token:tok-7".equals(key)) return tokenUser("7", "learner-seven");
            return Map.of();
        });

        login = new LoginInterceptor();
        mvc = chain(login, false);
    }

    private MockMvc chain(LoginInterceptor interceptor, boolean authRequired) {
        ReflectionTestUtils.setField(interceptor, "authRequired", authRequired);
        return MockMvcBuilders.standaloneSetup(map, plans, conversations)
                .setControllerAdvice(new GlobalExceptionHandler())
                .addInterceptors(new RefreshTokenInterceptor(redis), interceptor)
                .build();
    }

    @AfterEach
    void clearUser() {
        UserHolder.removeUser();
    }

    @Test
    void anonymousLearningMapDoesNotExposeUserOneSentences() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/learning-map"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
    }

    @Test
    void unresolvedBearerTokenDoesNotExposeUserOneSentences() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/learning-map").header("authorization", "Bearer missing"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
    }

    @Test
    void resolvedTokenReadsOwnMapInsteadOfUserOneSentences() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/learning-map").header("authorization", TOKEN_SEVEN));
        String body = body(result);
        assertEquals(200, result.getResponse().getStatus(), body);
        assertTrue(body.contains(USER_SEVEN_SENTENCE), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
    }

    @Test
    void anonymousContinuationDoesNotReturnUserOneQuotes() throws Exception {
        assertAuthOff();
        String nodeId = nodeId(TOKEN_ONE);
        MvcResult result = perform(get("/api/learning-map/nodes/" + nodeId + "/continuation"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
    }

    @Test
    void anonymousDecisionIsNotStoredAsUserOne() throws Exception {
        assertAuthOff();
        String suggestionId = suggestionId(TOKEN_ONE);
        MvcResult result = perform(post("/api/learning-map/suggestions/" + suggestionId + "/decision")
                .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertEquals(0, decisionCount(1));
        assertEquals(0, decisionCount(7));
    }

    @Test
    void resolvedTokenDecisionIsStoredUnderThatUser() throws Exception {
        assertAuthOff();
        String suggestionId = suggestionId(TOKEN_SEVEN);
        MvcResult result = perform(post("/api/learning-map/suggestions/" + suggestionId + "/decision")
                .header("authorization", TOKEN_SEVEN)
                .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}"));
        String body = body(result);
        assertEquals(200, result.getResponse().getStatus(), body);
        assertEquals(1, decisionCount(7));
        assertEquals(0, decisionCount(1));
    }

    @Test
    void foreignSuggestionIsNotAcceptedOntoUserOne() throws Exception {
        assertAuthOff();
        String suggestionId = suggestionId(TOKEN_ONE);
        MvcResult result = perform(post("/api/learning-map/suggestions/" + suggestionId + "/decision")
                .header("authorization", TOKEN_SEVEN)
                .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"accepted\"}"));
        String body = body(result);
        assertEquals(404, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
        assertEquals(0, decisionCount(1));
        assertEquals(0, decisionCount(7));
    }

    @Test
    void anonymousAdaptivePlansDoNotListUserOne() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/adaptive-plans"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_PLAN), body);
    }

    @Test
    void resolvedTokenListsOwnAdaptivePlan() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/adaptive-plans").header("authorization", TOKEN_SEVEN));
        String body = body(result);
        assertEquals(200, result.getResponse().getStatus(), body);
        assertTrue(body.contains(USER_SEVEN_PLAN), body);
        assertFalse(body.contains(USER_ONE_PLAN), body);
    }

    @Test
    void anonymousConversationMessagesDoNotReturnUserOneSentence() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/conversations/10/messages"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(SECRET_SENTENCE), body);
    }

    @Test
    void resolvedTokenCannotReadAnotherUsersChatSentence() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/conversations/10/messages").header("authorization", TOKEN_SEVEN));
        String body = body(result);
        assertEquals(403, result.getResponse().getStatus(), body);
        assertFalse(body.contains(SECRET_SENTENCE), body);
    }

    @Test
    void anonymousConversationCreateDoesNotPersistUserOne() throws Exception {
        assertAuthOff();
        MvcResult result = perform(post("/api/conversations").contentType(MediaType.APPLICATION_JSON).content("{}"));
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        verify(conversationWrites, never()).save(any());
    }

    @Test
    void resolvedTokenCreatesConversationUnderThatUser() throws Exception {
        assertAuthOff();
        MvcResult result = perform(post("/api/conversations")
                .header("authorization", TOKEN_SEVEN)
                .contentType(MediaType.APPLICATION_JSON).content("{\"user_id\":1}"));
        String body = body(result);
        assertEquals(200, result.getResponse().getStatus(), body);
        org.mockito.ArgumentCaptor<Conversation> saved = org.mockito.ArgumentCaptor.forClass(Conversation.class);
        verify(conversationWrites).save(saved.capture());
        assertEquals(7L, saved.getValue().getUserId());
    }

    @Test
    void realUserOneTokenStillReadsOwnChatSentence() throws Exception {
        assertAuthOff();
        MvcResult result = perform(get("/api/conversations/10/messages").header("authorization", TOKEN_ONE));
        String body = body(result);
        assertEquals(200, result.getResponse().getStatus(), body);
        assertTrue(body.contains(SECRET_SENTENCE), body);
    }

    @Test
    void authRequiredStillRejectsAnonymousMap() throws Exception {
        MockMvc strict = chain(new LoginInterceptor(), true);
        MvcResult result = strict.perform(get("/api/learning-map")).andReturn();
        String body = body(result);
        assertEquals(401, result.getResponse().getStatus(), body);
        assertFalse(body.contains(USER_ONE_SENTENCE), body);
    }

    private void assertAuthOff() {
        assertEquals(Boolean.FALSE, ReflectionTestUtils.getField(login, "authRequired"));
    }

    private MvcResult perform(MockHttpServletRequestBuilder request) throws Exception {
        return mvc.perform(request).andReturn();
    }

    private String body(MvcResult result) throws Exception {
        return result.getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

    private String nodeId(String token) throws Exception {
        JsonNode nodes = json.readTree(body(perform(get("/api/learning-map").header("authorization", token))))
                .path("data").path("nodes");
        assertTrue(nodes.isArray() && !nodes.isEmpty(), nodes.toString());
        return nodes.get(0).path("id").asText();
    }

    private String suggestionId(String token) throws Exception {
        JsonNode suggestions = json.readTree(body(perform(get("/api/learning-map").header("authorization", token))))
                .path("data").path("suggestions");
        assertTrue(suggestions.isArray() && !suggestions.isEmpty(), suggestions.toString());
        return suggestions.get(0).path("id").asText();
    }

    private int decisionCount(long userId) {
        try {
            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM learning_map_decision WHERE user_id=?", Integer.class, userId);
            return count == null ? 0 : count;
        } catch (DataAccessException ignored) {
            return 0;
        }
    }

    private void addMessage(long id, long conversationId, String text) {
        jdbc.update("INSERT INTO messages VALUES(?,?,'user',?,?)", id, conversationId, text,
                LocalDateTime.of(2026, 1, 1, 0, 0).plusMinutes(id));
    }

    private static String plan(String title) {
        return "{\"title\":\"" + title + "\",\"goal\":\"隔离验证\",\"dailyMinutes\":30,"
                + "\"modules\":[{\"title\":\"模块\",\"tasks\":[{\"title\":\"任务\",\"minutes\":20}]}]}";
    }

    private static Map<Object, Object> tokenUser(String id, String username) {
        Map<Object, Object> user = new HashMap<>();
        user.put("id", id);
        user.put("username", username);
        return user;
    }

    @SuppressWarnings("unchecked")
    private static <T> T proxy(Class<T> type, ProxyCall call) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, (target, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                if ("toString".equals(method.getName())) return type.getSimpleName() + "Proxy";
                if ("hashCode".equals(method.getName())) return System.identityHashCode(target);
                if ("equals".equals(method.getName())) return target == args[0];
            }
            return call.invoke(method, args == null ? new Object[0] : args);
        });
    }

    @FunctionalInterface
    private interface ProxyCall {
        Object invoke(java.lang.reflect.Method method, Object[] args) throws Throwable;
    }
}
