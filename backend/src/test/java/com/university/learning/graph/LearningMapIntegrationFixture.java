package com.university.learning.graph;

import com.university.learning.controller.LearningMapController;
import com.university.learning.common.GlobalExceptionHandler;
import com.university.learning.dto.UserDTO;
import com.university.learning.entity.*;
import com.university.learning.service.*;
import com.university.learning.utils.UserHolder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.lang.reflect.Proxy;
import java.time.LocalDateTime;
import java.util.*;

/** Test-only SQL adapters exercise production controller, extractor, memory and durable decision service without external infrastructure. */
public class LearningMapIntegrationFixture {
    public final JdbcTemplate jdbc;
    public final AgentMemoryService memory;
    public final MockMvc mvc;
    public LearningMapIntegrationFixture() {
        jdbc=new JdbcTemplate(new DriverManagerDataSource("jdbc:h2:mem:map_"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1"));
        jdbc.execute("CREATE TABLE conversations(id BIGINT PRIMARY KEY,user_id BIGINT,title VARCHAR(200),updated_at TIMESTAMP)");
        jdbc.execute("CREATE TABLE messages(id BIGINT PRIMARY KEY,conversation_id BIGINT,role VARCHAR(20),content VARCHAR(9000),created_at TIMESTAMP)");
        jdbc.update("INSERT INTO conversations VALUES(1,1,'学习地图测试会话',CURRENT_TIMESTAMP),(2,2,'另一个用户',CURRENT_TIMESTAMP)");
        add(1,1,"我想学习概率论"); add(2,1,"我想学习机器学习"); add(3,1,"概率论是什么？");
        add(4,1,"我的学习目标是理解概率论"); add(5,1,"请给我概率论练习题"); add(6,1,"我完成了概率论练习");
        add(7,2,"我想学习秘密主题");
        add(8,1,"我想学习线性代数"); add(9,1,"我想学习计算机图形学");
        memory=new AgentMemoryService(jdbc,true);
        IConversationService conversations=(IConversationService)Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{IConversationService.class},(proxy,method,args)-> {
            if(!method.getName().equals("listByUserId")) throw new UnsupportedOperationException(method.getName());
            return jdbc.query("SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",(rs,n)->new Conversation().setId(rs.getLong("id")).setUserId(rs.getLong("user_id")).setTitle(rs.getString("title")),args[0]);
        });
        IMessageService messages=(IMessageService)Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{IMessageService.class},(proxy,method,args)-> {
            if(!method.getName().equals("listRecentByConversationId")) throw new UnsupportedOperationException(method.getName());
            return jdbc.query("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC,id DESC LIMIT ?",(rs,n)->new Message().setId(rs.getLong("id")).setConversationId(rs.getLong("conversation_id")).setRole(rs.getString("role")).setContent(rs.getString("content")).setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime()),args[0],args[1]);
        });
        var controller=new LearningMapController(conversations,messages,memory,new LearningMapDecisionService(jdbc));
        mvc=MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new GlobalExceptionHandler()).addFilters((request,response,chain)-> {
            // Explicit test identity transport, not production authentication.
            var req=(jakarta.servlet.http.HttpServletRequest)request;
            String owner=req.getHeader("X-Test-User");
            try { if(owner!=null) { UserDTO user=new UserDTO();user.setId(Long.parseLong(owner));UserHolder.saveUser(user); } chain.doFilter(request,response); }
            finally { UserHolder.removeUser(); }
        }).build();
    }
    public void add(long id,long conversation,String text) { jdbc.update("INSERT INTO messages VALUES(?,?,'user',?,?)",id,conversation,text,LocalDateTime.of(2026,1,1,0,0).plusMinutes(id)); }
}
