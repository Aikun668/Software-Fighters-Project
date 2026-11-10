package com.university.learning.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import java.util.regex.*;

/** Durable, user-sourced learning memory. */
@Service
public class AgentMemoryService {
    private static final Logger log = LoggerFactory.getLogger(AgentMemoryService.class);
    private static final Map<String,String> LABELS = new LinkedHashMap<>();
    private static final Map<String,String> ALIASES = new LinkedHashMap<>();
    private static final Pattern UNSAFE = Pattern.compile(
        "密码|口令|密钥|令牌|验证码|身份证|护照|银行卡|信用卡|账号|帐号|账户|病历|病史|患有|诊断|用药|服用|药物|疾病|糖尿病|抑郁症|" +
        "忽略.{0,16}(?:指令|规则|提示)|忘记.{0,16}(?:指令|规则)|系统提示|开发者指令|绕过|越狱|" +
        "password|passwd|secret|api[_ -]?key|access[_ -]?token|bearer\\s|private[_ -]?key|" +
        "ignore.{0,30}(?:instructions|rules|prompt)|system\\s+prompt|system\\s*:|<\\|im_start\\|>|\\[system\\]|" +
        "(?<!\\d)\\d{15,19}[0-9Xx]?(?!\\d)|sk-[A-Za-z0-9_-]{8,}", Pattern.CASE_INSENSITIVE);
    private static final Pattern QUESTION = Pattern.compile("[？?]|^(?:假设|如果|老师说|他说|她说|你说)|(?:是什么|什么目标|学什么)$");
    static {
        LABELS.put("learning_goal", "学习目标"); LABELS.put("current_topic", "当前主题");
        LABELS.put("blocker", "卡点"); LABELS.put("progress", "学习进度");
        LABELS.put("time_budget", "学习时间约束"); LABELS.put("preference", "偏好"); LABELS.put("note", "备注");
        LABELS.forEach((key, label) -> { ALIASES.put(key, key); ALIASES.put(label, key); });
        ALIASES.put("目标", "learning_goal"); ALIASES.put("主题", "current_topic");
        ALIASES.put("进度", "progress"); ALIASES.put("学习时间", "time_budget");
        ALIASES.put("每天学习时长", "time_budget"); ALIASES.put("时间约束", "time_budget");
        ALIASES.put("每天学习时间", "time_budget");
        ALIASES.put("学习偏好", "preference");
    }
    private final JdbcTemplate jdbc;
    private final boolean enabled;
    private volatile boolean initialized;

    public AgentMemoryService(JdbcTemplate jdbc, @Value("${agent.memory.enabled:true}") boolean enabled) {
        this.jdbc = jdbc; this.enabled = enabled;
    }
    public boolean isEnabled() { return enabled; }

    /** Read the same bounded context for server-side summaries, without observing synthetic messages. */
    public synchronized Map<String, Object> readContext(Long userId, Long conversationId) {
        if (!enabled) return Map.of();
        try {
            if (userId == null || conversationId == null) throw new IllegalArgumentException("Missing identity");
            initialize();
            return snapshot(userId, conversationId);
        } catch (Exception failure) {
            log.warn("Agent memory unavailable: {}", failure.getClass().getSimpleName());
            Map<String,Object> context = emptyContext(userId, conversationId);
            context.put("available", false);
            return context;
        }
    }

    /** Only call for a user-authored message AFTER persistence assigns its real ID. */
    public synchronized Map<String, Object> observe(Long userId, Long conversationId, Long messageId, String text) {
        if (!enabled) return Map.of();
        Parsed parsed = parse(text);
        try {
            if (userId == null || conversationId == null || messageId == null || messageId <= 0) {
                throw new IllegalArgumentException("Missing persisted source");
            }
            initialize();
            TransactionTemplate tx = new TransactionTemplate(new DataSourceTransactionManager(Objects.requireNonNull(jdbc.getDataSource())));
            return tx.execute(status -> {
                String reply = null;
                List<Long> cutoffs = jdbc.query("SELECT cutoff_message_id FROM agent_memory_boundary WHERE user_id=?", (rs,row) -> rs.getLong(1), userId);
                boolean superseded = !cutoffs.isEmpty() && messageId <= cutoffs.get(0);
                if (superseded && parsed.key != null) {
                    // A request can persist before a later forget, then arrive here afterwards.
                    // It must not resurrect revoked data. A newly persisted statement may opt in again.
                    if (parsed.command) reply = "该消息早于最近的记忆更改，未覆盖当前记忆。请用新消息重新说明需要保存的内容。";
                } else if (!safe(text)) {
                    if (parsed.command) reply = "未保存：内容涉及敏感信息或指令，不适合进入学习记忆。";
                } else if ("view".equals(parsed.action)) {
                    // The view text is assembled only from durable active facts below.
                } else if (parsed.key == null) {
                    if (parsed.command) reply = "未保存：请使用例如“记住：学习目标=通过软考”或“忘记：学习目标”。";
                } else if ("forget".equals(parsed.action)) {
                    forget(userId, conversationId, messageId, parsed.key);
                    reply = "已忘记“" + LABELS.get(parsed.key) + "”，后续回答不再使用它。原始聊天记录仍保留。";
                } else if (parsed.value.isBlank() || parsed.value.length() > 300 || text.length() > 400) {
                    if (parsed.command) reply = "未保存：记忆值需为1到300字，来源消息不超过400字。";
                } else {
                    save(userId, conversationId, messageId, text.trim(), parsed);
                    if (parsed.command) reply = ("correct".equals(parsed.action) ? "已更正" : "已记住")
                        + "“" + LABELS.get(parsed.key) + "”：" + parsed.value + "。";
                }
                Map<String,Object> result = snapshot(userId, conversationId);
                if ("view".equals(parsed.action) && safe(text)) reply = describe(result);
                if (reply != null && !parsed.mixed) result.put("command_reply", reply);
                return result;
            });
        } catch (Exception failure) {
            // Never log source text, values, credentials or database connection strings.
            log.warn("Agent memory unavailable: {}", failure.getClass().getSimpleName());
            Map<String,Object> result = emptyContext(userId, conversationId);
            result.put("available", false);
            if (parsed.command && !parsed.mixed) result.put("command_reply", "记忆操作失败，当前未能确认保存或删除，请稍后重试。");
            return result;
        }
    }

    /** Does not mutate raw chat records. A revocation drops all earlier model context conservatively. */
    public List<Map<String, Object>> filterHistory(List<Map<String, Object>> history, Map<String, Object> context) {
        if (!enabled) return history;
        if (context == null || Boolean.FALSE.equals(context.get("available"))) return List.of();
        long cutoff = number(context.get("history_cutoff_message_id"));
        Set<Long> suppressed = new HashSet<>();
        Object ids = context.get("suppressed_message_ids");
        if (ids instanceof Collection<?>) for (Object id : (Collection<?>) ids) suppressed.add(number(id));
        List<Map<String,Object>> result = new ArrayList<>();
        boolean unsafeTurn = false;
        for (Map<String,Object> item : history) {
            long id = number(item.get("id"));
            String role = Objects.toString(item.get("role"), "");
            String content = Objects.toString(item.get("content"), "");
            if ("user".equals(role)) unsafeTurn = !safe(content);
            if (unsafeTurn || !safe(content) || (cutoff > 0 && id <= cutoff) || suppressed.contains(id)) continue;
            result.add(item);
        }
        return result;
    }

    private void initialize() {
        if (initialized) return;
        jdbc.execute("CREATE TABLE IF NOT EXISTS agent_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, "
            + "memory_scope VARCHAR(16) NOT NULL, scope_id BIGINT NOT NULL, memory_key VARCHAR(40) NOT NULL, "
            + "memory_value VARCHAR(300) NOT NULL, active BOOLEAN NOT NULL, source_conversation_id BIGINT NOT NULL, "
            + "source_message_id BIGINT NOT NULL, source_quote VARCHAR(400) NOT NULL, updated_at TIMESTAMP(6) NOT NULL, "
            + "CONSTRAINT uq_agent_memory UNIQUE(user_id, memory_scope, scope_id, memory_key))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS agent_memory_boundary (user_id BIGINT PRIMARY KEY, cutoff_message_id BIGINT NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS agent_memory_suppressed (user_id BIGINT NOT NULL, message_id BIGINT NOT NULL, "
            + "conversation_id BIGINT NOT NULL, PRIMARY KEY(user_id, message_id))");
        initialized = true;
    }

    private List<Map<String,Object>> rows(Long user, String key) {
        return jdbc.query("SELECT memory_scope,scope_id,memory_value,source_message_id,source_conversation_id,active FROM agent_memory "
            + "WHERE user_id=? AND memory_key=?", (rs, row) -> {
                Map<String,Object> item = new HashMap<>();
                item.put("scope", rs.getString(1)); item.put("scopeId", rs.getLong(2)); item.put("value", rs.getString(3));
                item.put("messageId", rs.getLong(4)); item.put("conversationId", rs.getLong(5)); item.put("active", rs.getBoolean(6));
                return item;
            }, user, key);
    }

    private void save(Long user, Long conv, Long message, String quote, Parsed parsed) {
        // Keep an exact source excerpt, but do not replay explicitly negated old values.
        quote = quote.replaceFirst("[，,]\\s*(?:而)?不是.*$", "");
        List<Map<String,Object>> all = rows(user, parsed.key);
        List<Map<String,Object>> relevant = all.stream().filter(row -> "user".equals(row.get("scope"))
            || conv.equals(row.get("scopeId"))).toList();
        String scope = "remember".equals(parsed.action) ? "user" : "session";
        if ("correct".equals(parsed.action) && relevant.stream().anyMatch(row -> "user".equals(row.get("scope")) && Boolean.TRUE.equals(row.get("active")))) scope = "user";
        final String targetScope = scope;
        boolean replaces = relevant.stream().anyMatch(row -> Boolean.TRUE.equals(row.get("active")) && !parsed.value.equals(row.get("value")));
        if (replaces || "correct".equals(parsed.action)) boundary(user, message);
        for (Map<String,Object> row : relevant) {
            if (Boolean.TRUE.equals(row.get("active"))) suppress(user, row);
        }
        // Explicit corrections update both current-session and long-term instances; other sessions remain scoped.
        if ("correct".equals(parsed.action)) {
            for (Map<String,Object> row : relevant) if (Boolean.TRUE.equals(row.get("active"))) {
                upsert(user, (String) row.get("scope"), (Long) row.get("scopeId"), parsed.key, parsed.value, conv, message, quote, true);
            }
        }
        if ("remember".equals(parsed.action)) {
            // A previously inferred session value must not shadow the explicit long-term choice.
            jdbc.update("UPDATE agent_memory SET active=FALSE,memory_value='',source_quote='',source_message_id=?,updated_at=? "
                + "WHERE user_id=? AND memory_scope='session' AND scope_id=? AND memory_key=?", message, Timestamp.from(Instant.now()), user, conv, parsed.key);
        }
        upsert(user, targetScope, "user".equals(targetScope) ? 0L : conv, parsed.key, parsed.value, conv, message, quote, true);
    }

    private void forget(Long user, Long conv, Long message, String key) {
        for (Map<String,Object> row : rows(user, key)) if (Boolean.TRUE.equals(row.get("active"))) suppress(user, row);
        // Forgetting a field is user-wide, including dormant session values, so switching sessions cannot revive it.
        jdbc.update("UPDATE agent_memory SET active=FALSE,memory_value='',source_quote='',source_message_id=?,updated_at=? "
            + "WHERE user_id=? AND memory_key=?", message, Timestamp.from(Instant.now()), user, key);
        upsert(user, "user", 0L, key, "", conv, message, "忘记：" + LABELS.get(key), false);
        boundary(user, message);
    }

    private void suppress(Long user, Map<String,Object> row) {
        int found = jdbc.update("UPDATE agent_memory_suppressed SET conversation_id=? WHERE user_id=? AND message_id=?",
            row.get("conversationId"), user, row.get("messageId"));
        if (found == 0) jdbc.update("INSERT INTO agent_memory_suppressed(user_id,message_id,conversation_id) VALUES(?,?,?)", user, row.get("messageId"), row.get("conversationId"));
    }

    private void boundary(Long user, Long message) {
        int found = jdbc.update("UPDATE agent_memory_boundary SET cutoff_message_id=CASE WHEN cutoff_message_id<? THEN ? ELSE cutoff_message_id END WHERE user_id=?", message, message, user);
        if (found == 0) jdbc.update("INSERT INTO agent_memory_boundary(user_id,cutoff_message_id) VALUES(?,?)", user, message);
    }

    private void upsert(Long user, String scope, Long scopeId, String key, String value, Long conv, Long message, String quote, boolean active) {
        Timestamp now = Timestamp.from(Instant.now());
        int found = jdbc.update("UPDATE agent_memory SET memory_value=?,active=?,source_conversation_id=?,source_message_id=?,source_quote=?,updated_at=? "
            + "WHERE user_id=? AND memory_scope=? AND scope_id=? AND memory_key=?", value, active, conv, message, quote, now, user, scope, scopeId, key);
        if (found == 0) jdbc.update("INSERT INTO agent_memory(user_id,memory_scope,scope_id,memory_key,memory_value,active,source_conversation_id,source_message_id,source_quote,updated_at) "
            + "VALUES(?,?,?,?,?,?,?,?,?,?)", user, scope, scopeId, key, value, active, conv, message, quote, now);
    }

    private Map<String,Object> snapshot(Long user, Long conv) {
        Map<String,Object> result = emptyContext(user, conv);
        List<Map<String,Object>> candidates = jdbc.query("SELECT memory_key,memory_value,memory_scope,source_conversation_id,source_message_id,source_quote,updated_at "
            + "FROM agent_memory WHERE user_id=? AND active=TRUE AND (memory_scope='user' OR (memory_scope='session' AND scope_id=?)) "
            + "ORDER BY source_message_id DESC, CASE WHEN memory_scope='session' THEN 0 ELSE 1 END LIMIT 24", (rs, row) -> {
                Map<String,Object> fact = new LinkedHashMap<>();
                fact.put("key", rs.getString(1));
                fact.put("label", LABELS.get(rs.getString(1)));
                fact.put("value", rs.getString(2));
                fact.put("scope", "user".equals(rs.getString(3)) ? "global" : "session"); fact.put("source_conversation_id", rs.getLong(4)); fact.put("source_message_id", rs.getLong(5));
                fact.put("source_quote", rs.getString(6)); fact.put("updated_at", rs.getTimestamp(7).toInstant().toString());
                return fact;
            }, user, conv);
        Map<String,Map<String,Object>> selected = new LinkedHashMap<>();
        for (Map<String,Object> fact : candidates) {
            if (safe((String) fact.get("value")) && safe((String) fact.get("source_quote"))) selected.putIfAbsent((String) fact.get("key"), fact);
        }
        result.put("facts", selected.values().stream().limit(12).toList());
        List<Long> cutoff = jdbc.query("SELECT cutoff_message_id FROM agent_memory_boundary WHERE user_id=?", (rs,row) -> rs.getLong(1), user);
        result.put("history_cutoff_message_id", cutoff.isEmpty() ? 0L : cutoff.get(0));
        result.put("suppressed_message_ids", jdbc.query("SELECT message_id FROM agent_memory_suppressed WHERE user_id=? ORDER BY message_id DESC LIMIT 200", (rs,row) -> rs.getLong(1), user));
        return result;
    }

    private Map<String,Object> emptyContext(Long user, Long conv) {
        Map<String,Object> context = new LinkedHashMap<>();
        context.put("schema_version", 1); context.put("user_id", user); context.put("conversation_id", conv);
        context.put("facts", List.of()); context.put("suppressed_message_ids", List.of()); context.put("history_cutoff_message_id", 0L);
        context.put("available", true);
        return context;
    }

    @SuppressWarnings("unchecked") private String describe(Map<String,Object> result) {
        List<Map<String,Object>> facts = (List<Map<String,Object>>) result.get("facts");
        if (facts.isEmpty()) return "当前没有可用的学习记忆。";
        StringBuilder text = new StringBuilder("当前学习记忆：");
        for (Map<String,Object> fact : facts) text.append("\n- ").append(fact.get("label")).append("：").append(fact.get("value"))
            .append("（").append("global".equals(fact.get("scope")) ? "跨会话" : "本会话").append("；来源消息 ").append(fact.get("source_message_id")).append("）");
        return text.toString();
    }

    private boolean safe(String text) { return text != null && !UNSAFE.matcher(text).find(); }
    private long number(Object value) { return value instanceof Number ? ((Number) value).longValue() : 0L; }
    private String clean(String text) { return text == null ? "" : text.trim().replaceAll("[。！!；;]+$", "").trim(); }

    private Parsed parse(String original) {
        String text = clean(original);
        if (text.matches("(?:请)?(?:查看|显示|列出)(?:我的)?(?:学习)?记忆")) return new Parsed("view", null, "", true, false);
        boolean mixed = false;
        Matcher remainder = Pattern.compile("[，,；;。]\\s*(?:再|然后|另外|并且).+").matcher(text);
        if (remainder.find()) { text = text.substring(0, remainder.start()); mixed = true; }
        String action = "observe";
        boolean command = false;
        if (text.matches("^(?:不对|更正一下)[，,：:].+")) {
            action = "correct"; command = true;
            text = text.replaceFirst("^(?:不对|更正一下)[，,：:]\\s*", "");
            text = text.replaceFirst("[，,]\\s*(?:而)?不是.*$", "");
        }
        Matcher prefix = Pattern.compile("^(?:请)?(记住|更正|修改|忘记|删除)(?:一下)?[：:\\s]*").matcher(text);
        if (prefix.find()) {
            command = true;
            action = switch (prefix.group(1)) { case "记住" -> "remember"; case "更正", "修改" -> "correct"; default -> "forget"; };
            text = clean(text.substring(prefix.end()));
        }
        if ("forget".equals(action)) return new Parsed(action, alias(text), "", true, mixed);
        if (QUESTION.matcher(text).find()) return new Parsed(action, null, "", command, mixed);
        Matcher correction = Pattern.compile("^(?:我的?|我)?(.{2,16}?)(?:改成|改为|更正为|修改为)[：:\\s]*(.+)$").matcher(text);
        if (correction.matches() && alias(correction.group(1)) != null) {
            return new Parsed("correct", alias(correction.group(1)), normalizeValue(correction.group(1), correction.group(2)), true, mixed);
        }
        Matcher labelled = Pattern.compile("^([^=：:]{1,40})[=：:]\\s*(.+)$").matcher(text);
        if (labelled.matches() && alias(labelled.group(1)) != null) return new Parsed(action, alias(labelled.group(1)), normalizeValue(labelled.group(1), labelled.group(2)), command, mixed);
        String[][] rules = {
            {"learning_goal", "^(?:我的?|我(?:目前|现在|这学期|今年|这个月)的)?(?:学习)?目标(?:是|为|在于)\\s*(.+)$"},
            {"learning_goal", "^我(?:希望|计划|想要)(.*(?:通过|完成|学会|掌握).*)$"},
            {"current_topic", "^我(?:现在|目前|最近)?(?:正在|在)(?:学习|学|复习)\\s*(.+)$"},
            {"blocker", "^我(?:目前|现在)?(?:卡在|困在|不理解|不明白|还不理解|还不明白|总是弄不清|弄不清|还是分不清|分不清)\\s*(.+)$"},
            {"progress", "^我(?:已经|目前|现在)?(?:学完了?|完成了?|学到了?)\\s*(.+)$"},
            {"time_budget", "^我每天(?:只能|只有|能|可以|可)?(?:花|学|学习)?\\s*((?:\\d+(?:\\.\\d+)?|[一二三四五六七八九十半]+)\\s*(?:分钟|小时|个小时))(?:学习时间|学习|学)?$"},
            {"preference", "^我(?:学习时)?(?:偏好|喜欢)(?:用)?\\s*(.+)$"}
        };
        Matcher weekly = Pattern.compile("^我每周(?:只能|只有|能|可以|可)?(?:抽出|花|学|学习)?\\s*((?:\\d+(?:\\.\\d+)?|[一二三四五六七八九十半]+)\\s*(?:分钟|小时|个小时))(?:复习|学习时间|学习|学)?$").matcher(text);
        if (weekly.matches()) return new Parsed(action, "time_budget", "每周" + weekly.group(1), command, mixed);
        for (String[] rule : rules) {
            Matcher match = Pattern.compile(rule[1]).matcher(text);
            if (match.matches()) {
                String value = clean(match.group(1));
                if ("time_budget".equals(rule[0])) value = "每天" + value;
                if ("progress".equals(rule[0]) && value.contains("接下来")) value = "已学完" + value;
                return new Parsed(action, rule[0], value, command, mixed);
            }
        }
        return new Parsed(action, null, "", command, mixed);
    }
    private String alias(String label) {
        String key = clean(label).replaceFirst("^我的?", "");
        return ALIASES.get(key);
    }
    private String normalizeValue(String label, String value) {
        value = clean(value);
        if ("time_budget".equals(alias(label)) && !value.startsWith("每天") && !value.startsWith("每周")) {
            if (label.contains("每天")) return "每天" + value;
            if (label.contains("每周")) return "每周" + value;
        }
        return value;
    }
    private record Parsed(String action, String key, String value, boolean command, boolean mixed) { }
}
