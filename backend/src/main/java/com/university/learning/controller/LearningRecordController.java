package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.LearningRecord;
import com.university.learning.service.ILearningRecordService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/record")
@RequiredArgsConstructor
public class LearningRecordController {

    private final ILearningRecordService learningRecordService;

    @Operation(summary = "获取当前用户所有学习记录")
    @GetMapping("/list")
    public Result listRecords() {
        Long userId = getUserId();
        List<LearningRecord> records = learningRecordService.listByUserId(userId);
        return Result.ok(records);
    }

    @Operation(summary = "按类型获取学习记录", description = "type: course_doc/mind_map/exercise/reading/code_practice")
    @GetMapping("/list/{type}")
    public Result listByType(@PathVariable String type) {
        Long userId = getUserId();
        List<LearningRecord> records = learningRecordService.listByUserIdAndType(userId, type);
        return Result.ok(records);
    }

    @Operation(summary = "获取某个资源的学习记录")
    @GetMapping("/resource/{resourceId}")
    public Result getRecord(@PathVariable Long resourceId) {
        Long userId = getUserId();
        LearningRecord record = learningRecordService.getByUserAndResource(userId, resourceId);
        if (record == null) {
            return Result.fail("学习记录不存在");
        }
        return Result.ok(record);
    }

    @Operation(summary = "获取学习统计", description = "返回总得分、平均分、总记录数")
    @GetMapping("/stats")
    public Result getStats() {
        Long userId = getUserId();

        Map<String, Object> stats = new HashMap<>();
        stats.put("totalScore", learningRecordService.getTotalScore(userId));
        stats.put("averageScore", learningRecordService.getAverageScore(userId));
        stats.put("totalRecords", learningRecordService.listByUserId(userId).size());

        return Result.ok(stats);
    }

    private Long getUserId() {
        return UserHolder.getUser().getId();
    }
}
