package com.university.learning.graph;

import com.fasterxml.jackson.databind.*;
import org.springframework.http.*;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Test-only newline protocol. Real H2 + production controller/decision/memory service, no network listener. */
public final class LearningMapBrowserBridge {
    public static void main(String[] args) throws Exception {
        var fixture=new LearningMapIntegrationFixture();
        var json=new ObjectMapper();
        var reader=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));
        System.out.println("MAP_READY");
        String line;
        while((line=reader.readLine())!=null) {
            try {
                JsonNode input=json.readTree(line);
                String path=input.path("path").asText("/api/learning-map");
                if(!path.equals("/api/learning-map") && !path.startsWith("/api/learning-map/")) {
                    System.out.println("MAP_RESULT {\"status\":404,\"body\":{\"message\":\"Test bridge only exposes learning-map routes\"}}");
                    System.out.flush(); continue;
                }
                String user=input.path("user").asText("1");
                var request=MockMvcRequestBuilders.request(HttpMethod.valueOf(input.path("method").asText("GET")),path).characterEncoding("UTF-8");
                if(!user.equals("anonymous")) request.header("X-Test-User",user);
                if(input.has("body")) request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(input.get("body")));
                var response=fixture.mvc.perform(request).andReturn().getResponse();
                String content=response.getContentAsString(StandardCharsets.UTF_8);
                Object body=content.isBlank() ? Map.of() : json.readTree(content);
                System.out.println("MAP_RESULT "+json.writeValueAsString(Map.of("status",response.getStatus(),"body",body)));
            } catch(Exception error) {
                System.out.println("MAP_RESULT "+json.writeValueAsString(Map.of("status",500,"body",Map.of("message",error.getClass().getSimpleName()))));
            }
            System.out.flush();
        }
    }
}
