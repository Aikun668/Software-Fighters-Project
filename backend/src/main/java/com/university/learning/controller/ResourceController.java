package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.Resource;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;

@Slf4j
@RestController
@RequestMapping("/api/resources")
@RequiredArgsConstructor
public class ResourceController {

    private final PythonClient pythonClient;
    private final IResourceService resourceService;
    private final IStudentProfileService profileService;

    /**
     * 生成学习资源（SSE流式 + 自动存库）
     */
    @PostMapping("/generate")
    public SseEmitter generateResources(@RequestBody Map<String, String> request) {
        Long userId = getUserId();
        String topic = request.get("topic");
        Map<String, Object> profileMap = buildProfileMap(userId);

        return pythonClient.generateResourcesStream(userId, topic, profileMap, (doneData) -> {
            saveResourcesToDb(userId, topic, doneData);
        });
    }

    @GetMapping("/list")
    public Result listResources() {
        Long userId = getUserId();
        List<Resource> resources = resourceService.listByUserId(userId);
        return Result.ok(resources);
    }

    @GetMapping("/list/{type}")
    public Result listByType(@PathVariable String type) {
        Long userId = getUserId();
        List<Resource> resources = resourceService.listByType(userId, type);
        return Result.ok(resources);
    }

    @GetMapping("/{resourceId}")
    public Result getResource(@PathVariable Long resourceId) {
        try {
            Resource resource = resourceService.getResourceDetail(resourceId);
            return Result.ok(resource);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @DeleteMapping("/{resourceId}")
    public Result deleteResource(@PathVariable Long resourceId) {
        try {
            Resource resource = resourceService.getById(resourceId);
            if (resource == null) {
                return Result.fail("资源不存在");
            }
            resourceService.removeById(resourceId);
            return Result.ok("删除成功");
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @PostMapping("/export-pptx")
    public Result exportPptx(@RequestBody Map<String, Object> request) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> contentBlocks = (List<Map<String, Object>>) request.get("content_blocks");
            String title = (String) request.getOrDefault("title", "AI学习资源");
            Map<String, Object> result = pythonClient.exportPptx(contentBlocks, title);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 保存资源到数据库（回调方法）
     */
    private void saveResourcesToDb(Long userId, String topic, Map<String, Object> doneData) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> blocks = (List<Map<String, Object>>) doneData.get("content_blocks");
            if (blocks == null) return;

            for (Map<String, Object> block : blocks) {
                Resource resource = new Resource();
                resource.setUserId(userId);
                resource.setType((String) block.getOrDefault("type", "course_doc"));
                resource.setTopic(topic);
                resource.setContentJson(block);
                resourceService.save(resource);
            }
            log.info("资源已保存: userId={}, topic={}, count={}", userId, topic, blocks.size());
        } catch (Exception e) {
            log.error("保存资源失败: userId={}, topic={}", userId, topic, e);
        }
    }

    private Map<String, Object> buildProfileMap(Long userId) {
        StudentProfile profile = profileService.getByUserId(userId);
        if (profile == null) return new HashMap<>();

        Map<String, Object> map = new HashMap<>();
        map.put("knowledge_base", profile.getKnowledgeBase());
        map.put("cognitive_style", profile.getCognitiveStyle());
        map.put("learning_goal", profile.getLearningGoal());
        map.put("weak_points", profile.getWeakPoints());
        map.put("learning_pace", profile.getLearningPace());
        map.put("interest_direction", profile.getInterestDirection());
        return map;
    }

    private Long getUserId() {

        return UserHolder.getUser().getId();
    }
}