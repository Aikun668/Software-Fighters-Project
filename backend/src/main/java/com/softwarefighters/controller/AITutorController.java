package com.softwarefighters.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import java.util.Map;

@RestController
@RequestMapping("/api/tutor")
public class AITutorController {

    private final WebClient aiClient;

    public AITutorController(@Value("${ai-service.base-url}") String aiBaseUrl) {
        this.aiClient = WebClient.create(aiBaseUrl);
    }

    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> tutorChat(@RequestBody Map<String, Object> request) {
        return aiClient.post()
                .uri("/tutor/chat")
                .bodyValue(request)
                .retrieve()
                .bodyToFlux(String.class);
    }
}
