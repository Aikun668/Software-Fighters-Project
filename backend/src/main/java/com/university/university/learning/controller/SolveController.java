package com.university.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.dto.SolveRequest;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 解题控制器，分步解答数学/科学/逻辑问题（SSE流式）。
 * SSE事件: steps(解题步骤) → token(解答文字) → confidence(置信度) → done
 */
@Slf4j
@RestController
@RequestMapping("/api/solve")
@RequiredArgsConstructor
public class SolveController {

    private final PythonClient pythonClient;

    /**
     * 分步解答问题（SSE流式）
     */
    @Operation(summary = "分步解题", description = "分步解答数学/科学/逻辑问题，返回解题步骤+文字+置信度(SSE流式)")
    @PostMapping
    public SseEmitter solve(@RequestBody SolveRequest request) {
        Long userId = UserHolder.getUser().getId();
        String question = request.getQuestion();
        String context = request.getContext();

        return pythonClient.solveStream(question, context, userId, (doneData) -> {
            log.info("解题完成: userId={}, question={}", userId,
                    question != null && question.length() > 30 ? question.substring(0, 30) : question);
        });
    }
}
