package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.*;
import com.university.learning.graph.LearningMapExtractor;
import com.university.learning.graph.LearningMapFeatures;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;

/** User-owned live projection: no shared course skeleton, no generated mastery scores. */
@RestController
@RequestMapping("/api/learning-map")
@RequiredArgsConstructor
public class LearningMapController {
    private final IConversationService conversations;
    private final IMessageService messages;
    private final AgentMemoryService memory;
    private final LearningMapDecisionService decisions;

    @GetMapping
    public Result getMap() {
        if (UserHolder.getUser() == null || UserHolder.getUser().getId() == null)
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "请先登录");
        Long userId = UserHolder.getUser().getId();
        LearningMapExtractor graph = new LearningMapExtractor();
        List<LearningMapExtractor.Source> eventSources = new ArrayList<>();
        List<Conversation> owned = conversations.listByUserId(userId).stream()
                .filter(c -> Objects.equals(c.getUserId(), userId)).toList();
        boolean truncated = owned.size() > 100;
        int scanned = 0;
        for (Conversation conversation : owned.stream().limit(100).toList()) {
            Map<String,Object> context = memory.readContext(userId, conversation.getId());
            if (memory.isEnabled() && Boolean.FALSE.equals(context.get("available")))
                return Result.ok(Map.of("nodes", List.of(), "edges", List.of(), "meta", Map.of(
                        "unavailable", true, "reason", "记忆隐私边界暂不可读取，已暂停生成地图")));
            List<Message> batch = messages.listRecentByConversationId(conversation.getId(), 501);
            if (batch.size() > 500) truncated = true;
            List<Map<String,Object>> raw = new ArrayList<>();
            Map<String,Message> byId = new HashMap<>();
            List<Message> chronological = new ArrayList<>(batch.stream().limit(500).toList());
            chronological.sort(Comparator.comparing(Message::getId, Comparator.nullsLast(Comparator.naturalOrder())));
            for (Message m : chronological) {
                if (!Objects.equals(m.getConversationId(), conversation.getId()) || m.getId() == null) continue;
                raw.add(Map.of("id", m.getId(), "role", Objects.toString(m.getRole(), ""), "content", Objects.toString(m.getContent(), "")));
                byId.put(m.getId().toString(), m);
            }
            Set<String> allowed = new HashSet<>();
            for (Map<String,Object> safe : memory.filterHistory(raw, context)) {
                Message m = byId.get(safe.get("id").toString());
                if (m == null || !"user".equals(m.getRole())) continue;
                allowed.add(m.getId().toString());
                if (m.getContent() != null && m.getContent().length() > 8000) truncated = true;
                graph.observe(conversation.getId().toString(), m.getId().toString(), m.getContent(), timestamp(m));
                if (m.getContent()!=null && m.getContent().length()<=8000) {
                    var eventSource=new LearningMapExtractor.Source(conversation.getId().toString(),m.getId().toString(),m.getContent(),timestamp(m));
                    if(LearningMapFeatures.eventCandidate(eventSource)) {
                        eventSources.add(eventSource);
                        if(eventSources.size()>500) {
                            eventSources.sort(Comparator.comparing(LearningMapExtractor.Source::createdAt).reversed().thenComparing(source -> new java.math.BigInteger(source.messageId()),Comparator.reverseOrder()));
                            eventSources.remove(eventSources.size()-1); truncated=true;
                        }
                    }
                }
                scanned++;
            }
            // Facts contribute only if their exact provenance is still readable, owned and not forgotten.
            if (context.get("facts") instanceof Collection<?> facts) for (Object item : facts) {
                if (!(item instanceof Map<?,?> fact) || !Set.of("current_topic", "learning_goal").contains(fact.get("key"))) continue;
                String cid = Objects.toString(fact.get("source_conversation_id"), "");
                String mid = Objects.toString(fact.get("source_message_id"), "");
                String quote = Objects.toString(fact.get("source_quote"), "");
                String value = Objects.toString(fact.get("value"), "");
                Message source = byId.get(mid);
                if (!cid.equals(conversation.getId().toString()) || !allowed.contains(mid) || source == null
                        || quote.isBlank() || quote.length() > 400 || source.getContent() == null
                        || !source.getContent().contains(quote) || !quote.contains(value)) continue;
                graph.memory(value, new LearningMapExtractor.Source(cid, mid, quote, timestamp(source)));
            }
        }
        List<LearningMapFeatures.Suggestion> suggestions=LearningMapFeatures.suggestions(graph.nodes(), decisions.read(userId));
        List<LearningMapExtractor.Edge> edges=new ArrayList<>(graph.edges());
        for(var suggestion:suggestions) if("accepted".equals(suggestion.status())) edges.add(new LearningMapExtractor.Edge("confirmed-"+suggestion.id(),suggestion.source(),suggestion.target(),"user_confirmed",suggestion.sources().get(0)));
        List<LearningMapFeatures.Event> allEvents=eventSources.stream().map(source -> LearningMapFeatures.event(source,graph.nodes())).filter(Objects::nonNull)
                .sorted(Comparator.comparing(LearningMapFeatures.Event::occurredAt).reversed().thenComparing(event -> new java.math.BigInteger(event.sources().get(0).messageId()),Comparator.reverseOrder())).toList();
        return Result.ok(Map.of("nodes", graph.nodes(), "edges", edges, "events", allEvents.stream().limit(500).toList(), "suggestions", suggestions, "meta", Map.of(
                "extraction", "conservative-rules-v1", "truncated", truncated || graph.truncated() || allEvents.size()>500, "unavailable", false,
                "scannedUserMessages", scanned, "conversationLimit", 100, "messagesPerConversationLimit", 500,
                "description", "明确学习表达与可核对记忆生成节点；仅明确前置关系连线，不推断掌握度。")));
    }
    @SuppressWarnings("unchecked")
    @PostMapping("/suggestions/{id}/decision")
    public Result decide(@PathVariable String id,@RequestBody Map<String,String> body) {
        String decision=body.get("decision");
        if (!Set.of("accepted","rejected").contains(Objects.toString(decision,""))) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"请选择接受或拒绝");
        Map<String,Object> current=(Map<String,Object>)getMap().getData();
        List<LearningMapFeatures.Suggestion> available=(List<LearningMapFeatures.Suggestion>)current.getOrDefault("suggestions",List.of());
        if(available.stream().noneMatch(s -> s.id().equals(id))) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"关联建议已不可读取，请刷新地图");
        decisions.save(UserHolder.getUser().getId(),id,decision);
        return Result.ok(Map.of("id",id,"status",decision));
    }
    @SuppressWarnings("unchecked")
    @GetMapping("/nodes/{id}/continuation")
    public Result continuation(@PathVariable String id) {
        Map<String,Object> current=(Map<String,Object>)getMap().getData();
        List<LearningMapExtractor.Node> nodes=(List<LearningMapExtractor.Node>)current.get("nodes");
        LearningMapExtractor.Node node=nodes.stream().filter(n -> n.id().equals(id)).findFirst().orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND,"节点来源已不可读取，请刷新地图"));
        return Result.ok(Map.of("draft",LearningMapFeatures.continuation(node,nodes,(List<LearningMapExtractor.Edge>)current.get("edges"))));
    }
    @ExceptionHandler(org.springframework.dao.DataAccessException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public Result persistenceUnavailable() { return Result.fail(503,"学习地图存储暂不可用，请稍后重试；未保存关联决定"); }
    private String timestamp(Message m) { return m.getCreatedAt() == null ? "" : m.getCreatedAt().toString(); }
}
