package com.university.learning.plan;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.university.learning.controller.AdaptivePlanController;
import com.university.learning.service.AdaptivePlanService;
import com.university.learning.utils.LoginInterceptor;
import com.university.learning.utils.RefreshTokenInterceptor;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * P0 回归：/api/adaptive-plans 必须走真实的登录拦截器链（RefreshTokenInterceptor -> LoginInterceptor），
 * 不再像 AdaptivePlanServiceTest / AdaptivePlanBrowserBridge 那样直接传 userId 或塞 X-Test-User 绕过拦截器。
 */
class AdaptivePlanAuthInterceptorTest {

    private static final String PLAN_BODY = "{\"title\":\"数据库\",\"goal\":\"掌握事务\",\"dailyMinutes\":30,"
            + "\"modules\":[{\"title\":\"隔离级别\",\"tasks\":[{\"title\":\"幻读例子\",\"minutes\":45}]}]}";

    private final ObjectMapper mapper = new ObjectMapper();
    private LoginInterceptor login;
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        JdbcTemplate jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        AdaptivePlanService service = new AdaptivePlanService(jdbc, mapper);

        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        HashOperations<String, Object, Object> hash = mock(HashOperations.class);
        when(redis.opsForHash()).thenReturn(hash);
        // 默认：token 不在 Redis 里（未登录或已过期）
        when(hash.entries(anyString())).thenReturn(Map.of());
        when(hash.entries("login:token:token-7")).thenReturn(Map.of("id", "7", "username", "u7"));
        when(hash.entries("login:token:token-8")).thenReturn(Map.of("id", "8", "username", "u8"));

        login = new LoginInterceptor();
        mvc = MockMvcBuilders.standaloneSetup(new AdaptivePlanController(service))
                .addInterceptors(new RefreshTokenInterceptor(redis), login)
                .build();
    }

    private void authRequired(boolean value) {
        ReflectionTestUtils.setField(login, "authRequired", value);
    }

    private JsonNode json(String body) throws Exception {
        return mapper.readTree(body);
    }

    private String listBody(String token) throws Exception {
        return mvc.perform(get("/api/adaptive-plans").header("authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
    }

    @Test
    void shippedDefaultRequiresLogin() {
        new ApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .run(context -> {
                    String value = context.getEnvironment().getProperty("learning.auth.required");
                    assertNotNull(value, "application.yml 里缺少 learning.auth.required");
                    assertTrue(Boolean.parseBoolean(value),
                            "learning.auth.required 默认必须是 true，实际为 " + value
                                    + "（免登录模式会让所有人共用 user 1）");
                });
    }

    @Test
    void unauthenticatedRequestsAreRejectedWhenLoginRequired() throws Exception {
        authRequired(true);
        mvc.perform(get("/api/adaptive-plans")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/adaptive-plans").contentType(APPLICATION_JSON).content(PLAN_BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownTokenIsRejectedWhenLoginRequired() throws Exception {
        authRequired(true);
        mvc.perform(get("/api/adaptive-plans").header("authorization", "Bearer not-a-real-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void devFallbackStillWorksWhenLoginDisabled() throws Exception {
        authRequired(false);
        mvc.perform(post("/api/adaptive-plans").contentType(APPLICATION_JSON).content(PLAN_BODY))
                .andExpect(status().isOk());
        // 匿名请求落到兜底的 dev_user(1)
        String anonymousList = mvc.perform(get("/api/adaptive-plans"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertEquals(1, json(anonymousList).path("data").size(), "免登录兜底应落到 user 1 的计划上");
    }

    /** P0 核心回归：免登录兜底不得把已由 token 还原出来的真实用户盖成 user 1。 */
    @Test
    void devFallbackNeverOverwritesRestoredLoginUser() throws Exception {
        authRequired(false);
        mvc.perform(post("/api/adaptive-plans").header("authorization", "Bearer token-7")
                        .contentType(APPLICATION_JSON).content(PLAN_BODY))
                .andExpect(status().isOk());

        assertEquals(1, json(listBody("token-7")).path("data").size(), "user 7 应看到自己的计划");
        assertEquals(0, json(listBody("token-8")).path("data").size(), "user 8 不应看到 user 7 的计划");
    }

    @Test
    void crossUserAccessIs404ThroughInterceptorChain() throws Exception {
        authRequired(false);
        String created = mvc.perform(post("/api/adaptive-plans").header("authorization", "Bearer token-7")
                        .contentType(APPLICATION_JSON).content(PLAN_BODY))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String planId = json(created).path("data").path("id").asText();

        mvc.perform(get("/api/adaptive-plans/" + planId).header("authorization", "Bearer token-7"))
                .andExpect(status().isOk());
        mvc.perform(get("/api/adaptive-plans/" + planId).header("authorization", "Bearer token-8"))
                .andExpect(status().isNotFound());
    }

    @Test
    void writingAnotherUsersPlanIs404ThroughInterceptorChain() throws Exception {
        authRequired(false);
        String created = mvc.perform(post("/api/adaptive-plans").header("authorization", "Bearer token-7")
                        .contentType(APPLICATION_JSON).content(PLAN_BODY))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String planId = json(created).path("data").path("id").asText();

        mvc.perform(post("/api/adaptive-plans/" + planId + "/proposals")
                        .header("authorization", "Bearer token-8")
                        .contentType(APPLICATION_JSON)
                        .content("{\"version\":1,\"message\":\"每天20分钟\"}"))
                .andExpect(status().isNotFound());
    }
}
