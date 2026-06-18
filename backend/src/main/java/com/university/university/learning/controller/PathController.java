package com.university.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IStudentProfileService;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/path")
@RequiredArgsConstructor
public class PathController {

    private final PythonClient pythonClient;
    private final IStudentProfileService profileService;

    @Operation(summary = "获取学习路径规划", description = "AI 根据用户画像生成个性化学习路径")
    @GetMapping("/{userId}")
    public Result getLearningPath(@PathVariable Long userId,
                                   @RequestParam(required = false) String topic) {
        try {
            // 获取学生画像快照传给 Python
            StudentProfile profile = profileService.getByUserId(userId);
            @SuppressWarnings("unchecked")
            Map<String, Object> profileMap = profile != null && profile.getRawProfileJson() instanceof Map
                    ? (Map<String, Object>) profile.getRawProfileJson()
                    : null;
            Map<String, Object> path = pythonClient.getLearningPath(userId, topic, profileMap);
            return Result.ok(path);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }
}
