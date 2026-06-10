package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/path")
@RequiredArgsConstructor
public class PathController {

    private final PythonClient pythonClient;

    /**
     * 学习路径规划
     */
    @GetMapping("/{userId}")
    public Result getLearningPath(@PathVariable Long userId) {
        try {
            Map<String, Object> path = pythonClient.getLearningPath(userId);
            return Result.ok(path);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }
}