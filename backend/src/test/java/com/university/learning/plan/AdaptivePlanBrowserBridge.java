package com.university.learning.plan;

import com.fasterxml.jackson.databind.*;
import org.springframework.http.*;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Test-only newline protocol. Real H2 + production adaptive-plan controller/service, no network listener. */
public final class AdaptivePlanBrowserBridge {
    public static void main(String[] args) throws Exception {
        var jdbc=new org.springframework.jdbc.core.JdbcTemplate(new org.springframework.jdbc.datasource.DriverManagerDataSource("jdbc:h2:mem:adaptive_browser;MODE=MySQL;DB_CLOSE_DELAY=-1"));
        var service=new com.university.learning.service.AdaptivePlanService(jdbc,new ObjectMapper());
        var mvc=org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(new com.university.learning.controller.AdaptivePlanController(service))
            .setControllerAdvice(new com.university.learning.common.GlobalExceptionHandler())
            .addFilters((request,response,chain)->{
                String user=((jakarta.servlet.http.HttpServletRequest)request).getHeader("X-Test-User");
                try {
                    if(user!=null){var identity=new com.university.learning.dto.UserDTO();identity.setId(Long.parseLong(user));com.university.learning.utils.UserHolder.saveUser(identity);}
                    chain.doFilter(request,response);
                } finally {com.university.learning.utils.UserHolder.removeUser();}
            }).build();
        var json=new ObjectMapper();
        var reader=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));
        System.out.println("PLAN_READY");
        String line;
        while((line=reader.readLine())!=null) {
            try {
                JsonNode input=json.readTree(line);
                String path=input.path("path").asText("/api/adaptive-plans");
                if(!path.equals("/api/adaptive-plans") && !path.startsWith("/api/adaptive-plans/")) {
                    System.out.println("PLAN_RESULT {\"status\":404,\"body\":{\"message\":\"Test bridge only exposes adaptive-plan routes\"}}");
                    System.out.flush(); continue;
                }
                String user=input.path("user").asText("1");
                var request=MockMvcRequestBuilders.request(HttpMethod.valueOf(input.path("method").asText("GET")),path).characterEncoding("UTF-8");
                if(!user.equals("anonymous")) request.header("X-Test-User",user);
                if(input.has("body")) request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(input.get("body")));
                var response=mvc.perform(request).andReturn().getResponse();
                String content=response.getContentAsString(StandardCharsets.UTF_8);
                Object body=content.isBlank() ? Map.of() : json.readTree(content);
                System.out.println("PLAN_RESULT "+json.writeValueAsString(Map.of("status",response.getStatus(),"body",body)));
            } catch(Exception error) {
                System.out.println("PLAN_RESULT "+json.writeValueAsString(Map.of("status",500,"body",Map.of("message",error.getClass().getSimpleName()))));
            }
            System.out.flush();
        }
    }
}
