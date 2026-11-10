package com.university.learning.graph;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;

/** Conservative, deterministic projection. It never claims mastery or infers edges from proximity. */
public final class LearningMapExtractor {
    public record Source(String conversationId, String messageId, String quote, String createdAt) {}
    public record Node(String id, String title, String summary, List<Source> sources, String firstSeen, String lastSeen) {}
    public record Edge(String id, String source, String target, String relation, Source evidence) {}
    private boolean truncated;
    public boolean truncated() { return truncated; }
    private final Map<String, Node> nodes = new LinkedHashMap<>();
    private final Map<String, Edge> edges = new LinkedHashMap<>();
    private static final Pattern TAG = Pattern.compile("\\[\\[([^\\[\\]\\n]{1,60})]]");
    private static final Pattern TOPIC = Pattern.compile("^(?:我(?:现在|目前|最近)?(?:正在|在|想|想要)?(?:学习|学|复习)|(?:请)?(?:解释一下|解释|讲讲|介绍一下)|什么是|学习主题[：:])\\s*(.{1,60}?)(?:是什么|的概念|的基础)?[？?。！!]*$");
    private static final Pattern QUESTION = Pattern.compile("^(.{1,60}?)是什么[？?]*$");
    private static final Pattern RELATION = Pattern.compile("^(.{1,60}?)(依赖|是)(.{1,60}?)(的前置知识|的基础)?[。！!]*$");
    public void observe(String conversationId, String messageId, String text, String at) {
        if (text == null || text.length() > 8000) return;
        for (String sentence : text.split("[\\n。；;]")) {
            String s = sentence.trim();
            if (s.isEmpty() || s.length() > 200) continue;
            Source evidence = new Source(conversationId, messageId, s, at);
            Matcher tag = TAG.matcher(s);
            while (tag.find()) add(tag.group(1), evidence);
            Matcher topic = TOPIC.matcher(s);
            if (topic.matches()) add(topic.group(1), evidence);
            Matcher question = QUESTION.matcher(s);
            if (question.matches()) add(question.group(1), evidence);
            // These markers make a statement ambiguous, hypothetical or negated. Prefer no edge.
            if (s.matches(".*[？?不没否吗么未无吧何谁哪怎“”\"].*") || s.contains("如果") || s.contains("可能") || s.matches(".*(?:并非|是否|假设|也许|据说|未必|听说|应该|大概|似乎|或许|假如).*")) continue;
            Matcher r = RELATION.matcher(s);
            if (!r.matches()) continue;
            String left = r.group(1), verb = r.group(2), right = r.group(3), suffix = r.group(4);
            if (!"依赖".equals(verb) && suffix == null) continue;
            // Direction is dependent -> prerequisite, consistently for either sentence form.
            String source = add("依赖".equals(verb) ? left : right, evidence);
            String target = add("依赖".equals(verb) ? right : left, evidence);
            if (source == null || target == null || source.equals(target)) continue;
            String id = id(source + ":depends_on:" + target);
            if (edges.size() >= 1000 && !edges.containsKey(id)) { truncated = true; continue; }
            edges.putIfAbsent(id, new Edge(id, source, target, "depends_on", evidence));
        }
    }
    public void memory(String title, Source evidence) { add(title, evidence); }
    private String add(String raw, Source source) {
        String title = raw.replace("[[", "").replace("]]", "").trim().replaceAll("\\s+", " ");
        if (title.isEmpty() || title.length() > 60 || title.matches(".*[，,：:？?！!。；;\\n].*")
                || title.matches(".*(?:不要|忘记|密码|身份证|手机号|不想|不是|不学).*")) return null;
        String id = id(title.toLowerCase(Locale.ROOT));
        Node old = nodes.get(id);
        if (old == null && nodes.size() >= 500) { truncated = true; return null; }
        List<Source> sources = new ArrayList<>(old == null ? List.of() : old.sources());
        if (sources.stream().noneMatch(s -> s.conversationId().equals(source.conversationId()) && s.messageId().equals(source.messageId()))) sources.add(source);
        sources.sort(Comparator.comparing(Source::createdAt).thenComparing(s -> new java.math.BigInteger(s.messageId())));
        String firstSeen = sources.get(0).createdAt();
        if (old != null && old.firstSeen().compareTo(firstSeen) < 0) firstSeen = old.firstSeen();
        if (sources.size() > 20) { truncated = true; sources.remove(0); }
        nodes.put(id, new Node(id, old == null ? title : old.title(), "来自明确学习表达；不代表掌握程度", sources,
                firstSeen, sources.get(sources.size()-1).createdAt()));
        return id;
    }
    private static String id(String key) { return UUID.nameUUIDFromBytes(key.getBytes(StandardCharsets.UTF_8)).toString(); }
    public List<Node> nodes() { return List.copyOf(nodes.values()); }
    public List<Edge> edges() { return List.copyOf(edges.values()); }
}
