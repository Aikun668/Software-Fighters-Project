package com.university.learning.controller;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.*;
import com.university.learning.graph.LearningMapExtractor;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.junit.jupiter.api.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class LearningMapControllerTest {
    final IConversationService conversations = mock(IConversationService.class);
    final IMessageService messages = mock(IMessageService.class);
    final AgentMemoryService memory = mock(AgentMemoryService.class);
    final LearningMapController controller = new LearningMapController(conversations, messages, memory, mock(LearningMapDecisionService.class));
    @BeforeEach void setup() {
        UserDTO user = new UserDTO(); user.setId(1L); UserHolder.saveUser(user);
        when(conversations.listByUserId(1L)).thenReturn(List.of(new Conversation().setId(10L).setUserId(1L)));
        when(memory.readContext(1L,10L)).thenReturn(Map.of());
        when(memory.filterHistory(anyList(), anyMap())).thenAnswer(i -> i.getArgument(0));
        when(messages.listRecentByConversationId(10L,501)).thenReturn(List.of(msg(1L,"user","我想学习线性代数")));
    }
    Message msg(long id, String role, String text) { return new Message().setId(id).setConversationId(10L).setRole(role).setContent(text); }
    @AfterEach void cleanup() { UserHolder.removeUser(); }
    @SuppressWarnings("unchecked") Map<String,Object> result() { return (Map<String,Object>) controller.getMap().getData(); }
    @Test void rejectsMissingIdentity() {
        UserHolder.removeUser();
        assertEquals(401,assertThrows(ResponseStatusException.class,controller::getMap).getStatusCode().value());
        verifyNoInteractions(conversations,messages,memory);
    }
    @Test void onlyReadsOwnerAndNeverAssistantKnowledge() {
        when(conversations.listByUserId(1L)).thenReturn(List.of(new Conversation().setId(10L).setUserId(1L), new Conversation().setId(20L).setUserId(2L)));
        when(messages.listRecentByConversationId(10L,501)).thenReturn(List.of(msg(1,"user","我想学习线性代数"),msg(2,"assistant","机器学习依赖线性代数")));
        assertEquals(1,((List<?>)result().get("nodes")).size());
        assertTrue(((List<?>)result().get("edges")).isEmpty());
        verify(messages,never()).listRecentByConversationId(eq(20L),anyInt());
    }
    @Test void forgettingRemovesPreviouslyDerivedNode() {
        assertEquals(1,((List<?>)result().get("nodes")).size());
        when(memory.filterHistory(anyList(),anyMap())).thenReturn(List.of());
        assertTrue(((List<?>)result().get("nodes")).isEmpty());
    }
    @Test void unavailableMemoryFailsClosed() {
        when(memory.isEnabled()).thenReturn(true);
        when(memory.readContext(1L,10L)).thenReturn(Map.of("available",false));
        Map<String,Object> r=result();
        assertTrue(((List<?>)r.get("nodes")).isEmpty());
        assertEquals(true,((Map<?,?>)r.get("meta")).get("unavailable"));
        verifyNoInteractions(messages);
    }
    @Test void verifiedMemoryCannotForgeProvenance() {
        when(messages.listRecentByConversationId(10L,501)).thenReturn(List.of(msg(1,"user","记住：主题：量子计算")));
        Map<String,Object> fact=Map.of("key","current_topic","value","量子计算","source_quote","记住：主题：量子计算","source_conversation_id",10L,"source_message_id",1L);
        when(memory.readContext(1L,10L)).thenReturn(Map.of("facts",List.of(fact)));
        assertEquals(1,((List<?>)result().get("nodes")).size());
        when(memory.readContext(1L,10L)).thenReturn(Map.of("facts",List.of(Map.of("key","current_topic","value","私密主题","source_quote","私密主题","source_conversation_id",20L,"source_message_id",1L))));
        assertTrue(((List<?>)result().get("nodes")).isEmpty());
    }
    @Test void latestWindowIncludesNewTurnAndReportsTruncation() {
        List<Message> recent = new ArrayList<>();
        recent.add(msg(1001,"user","我想学习新主题"));
        for (long i=1000;i>=501;i--) recent.add(msg(i,"user","你好"));
        when(messages.listRecentByConversationId(10L,501)).thenReturn(recent);
        Map<String,Object> r=result();
        assertEquals(1,((List<?>)r.get("nodes")).size());
        assertEquals(true,((Map<?,?>)r.get("meta")).get("truncated"));
    }
    @Test void firstSeenIsIndependentOfConversationTraversalOrder() {
        var e = new LearningMapExtractor();
        e.observe("20", "20", "我想学习线性代数", "2026-02-01");
        e.observe("10", "10", "我想学习线性代数", "2026-01-01");
        assertEquals("2026-01-01",e.nodes().get(0).firstSeen());
        assertEquals("2026-02-01",e.nodes().get(0).lastSeen());
    }
    @Test void boundedGraphNeverHasDanglingEdgesAndKeepsLatestEvidence() {
        var e = new LearningMapExtractor();
        for (int i=1;i<=25;i++) e.observe("10",Integer.toString(i),"我想学习主题", "2026-01-01");
        assertEquals(20,e.nodes().get(0).sources().size());
        assertEquals("25",e.nodes().get(0).sources().get(19).messageId());
        for (int i=1;i<=510;i++) e.observe("10",Integer.toString(i+100),"我想学习概念"+i, "2026-01-02");
        e.observe("10","1000","新内容依赖另一个新内容", "2026-01-03");
        assertEquals(500,e.nodes().size()); assertTrue(e.truncated());
        Set<String> ids = new HashSet<>(); e.nodes().forEach(n -> ids.add(n.id()));
        assertTrue(e.edges().stream().allMatch(edge -> ids.contains(edge.source()) && ids.contains(edge.target())));
    }
    @Test void projectionSupportsOrdinaryQuestionsWithoutInventedRelations() {
        var e=new LearningMapExtractor();
        e.observe("10","1","我想学习线性代数",""); e.observe("10","2","我想学习Python","");
        e.observe("10","3","反向传播是什么？","");
        assertEquals(3,e.nodes().size()); assertTrue(e.edges().isEmpty());
        e.observe("10","4","线性代数是机器学习的前置知识","");
        assertEquals(4,e.nodes().size()); assertEquals(1,e.edges().size());
        e.observe("10","5","线性代数是机器学习的前置知识吗？","");
        e.observe("10","6","概率论不是机器学习的前置知识","");
        assertEquals(1,e.edges().size());
        for (String prefix : List.of("假设", "也许", "据说", "未必", "听说", "应该", "大概")) e.observe("10","8",prefix + "概率论依赖统计学", "");
        assertEquals(1,e.edges().size());
        for (String statement : List.of("机器学习无需依赖线性代数", "机器学习未依赖线性代数", "机器学习依赖线性代数对吧", "机器学习无须依赖线性代数", "机器学习并非依赖线性代数")) e.observe("10","9", statement, "");
        assertEquals(1,e.edges().size());
        e.observe("10","1","我想学习线性代数",""); assertEquals(4,e.nodes().size());
    }
}
