package com.university.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.dto.ExportRequest;
import com.university.learning.dto.ResourceGenRequest;
import com.university.learning.entity.LearningActivity;
import com.university.learning.entity.Resource;
import com.university.learning.entity.StudentProfile;
import com.university.learning.service.ILearningActivityService;
import com.university.learning.service.IResourceService;
import com.university.learning.service.IStudentProfileService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 学习资源控制器，处理课程文档、思维导图等资源的生成、查询、删除和导出。
 */
@Slf4j
@RestController
@RequestMapping("/api/resources")
@RequiredArgsConstructor
public class ResourceController {

    private final PythonClient pythonClient;
    private final IResourceService resourceService;
    private final IStudentProfileService profileService;
    private final ILearningActivityService activityService;
    private final RestTemplate restTemplate;

    private static final String PYTHON_BASE = "http://127.0.0.1:8001/internal";

    /**
     * 根据主题生成学习资源（SSE 流式），完成后自动入库。
     *
     * @param request 包含 topic 字段
     * @return SSE 流式响应
     */
    @Operation(summary = "生成学习资源", description = "根据 topic 生成课程文档/思维导图等(SSE 流式)，完成后自动入库。resource_type 可选，不传由AI自动判断")
    @PostMapping("/generate")
    public SseEmitter generateResources(@RequestBody ResourceGenRequest request) {
        Long userId = getUserId();
        String topic = request.getTopic();
        String resourceType = request.getResource_type();
        Map<String, Object> profileMap = buildProfileMap(userId);

        return pythonClient.generateResourcesStream(userId, topic, resourceType, profileMap, (doneData) -> {
            saveResourcesToDb(userId, topic, doneData);
            recordResourceActivity(userId);
        });
    }

    /**
     * 获取当前登录用户的所有资源列表。
     */
    @Operation(summary = "获取当前用户资源列表")
    @GetMapping("/list")
    public Result listResources() {
        Long userId = getUserId();
        List<Resource> resources = resourceService.listByUserId(userId);
        return Result.ok(resources);
    }

    /**
     * 按类型获取当前用户的资源列表。
     *
     * @param type 资源类型：course_doc / mind_map / exercise / reading / code_practice
     */
    @Operation(summary = "按类型获取资源列表", description = "type: course_doc/mind_map/exercise/reading/code_practice")
    @GetMapping("/list/{type}")
    public Result listByType(@PathVariable String type) {
        Long userId = getUserId();
        List<Resource> resources = resourceService.listByType(userId, type);
        return Result.ok(resources);
    }

    /**
     * 获取指定资源的详情（含 content_json）。
     */
    @Operation(summary = "获取资源详情")
    @GetMapping("/{resourceId}")
    public Result getResource(@PathVariable Long resourceId) {
        try {
            Resource resource = resourceService.getResourceDetail(resourceId);
            return Result.ok(resource);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 删除指定资源。
     */
    @Operation(summary = "删除资源")
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

    /**
     * 根据 content_blocks 导出 PPTX 文件。
     */
    @Operation(summary = "导出 PPTX", description = "根据 content_blocks 生成 PPTX 文件")
    @PostMapping("/export-pptx")
    public Result exportPptx(@RequestBody ExportRequest request) {
        try {
            String title = request.getTitle() != null ? request.getTitle() : "AI学习资源";
            Map<String, Object> result = pythonClient.exportPptx(request.getContent_blocks(), title);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 下载 PPTX 文件（代理 Python 的文件返回）。
     * 流程: 前端传 filename → Java 从 Python 下载 → 返回文件流
     */
    @Operation(summary = "下载 PPTX", description = "根据 filename 下载已生成的 PPTX 文件")
    @GetMapping("/download-pptx")
    public ResponseEntity<ByteArrayResource> downloadPptx(@RequestParam String filename) {
        try {
            String url = PYTHON_BASE + "/resources/download-pptx?filename=" + filename;
            ResponseEntity<byte[]> response = restTemplate.getForEntity(url, byte[].class);
            if (response.getBody() == null) {
                return ResponseEntity.notFound().build();
            }
            ByteArrayResource resource = new ByteArrayResource(response.getBody());
            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation"))
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            "attachment; filename=\"" + filename + "\"")
                    .body(resource);
        } catch (Exception e) {
            log.error("下载PPTX失败: filename={}", filename, e);
            return ResponseEntity.internalServerError().build();
        }
    }

    /**
     * 根据 content_blocks 导出 PDF 文件。
     */
    @Operation(summary = "导出 PDF", description = "根据 content_blocks 生成 PDF 文件")
    @PostMapping("/export-pdf")
    public Result exportPdf(@RequestBody ExportRequest request) {
        try {
            String title = request.getTitle() != null ? request.getTitle() : "AI学习资源";
            Map<String, Object> result = pythonClient.exportPdf(request.getContent_blocks(), title);
            return Result.ok(result);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 下载 PDF 文件（代理 Python 的文件返回）。
     */
    @Operation(summary = "下载 PDF", description = "根据 filename 下载已生成的 PDF 文件")
    @GetMapping("/download-pdf")
    public ResponseEntity<ByteArrayResource> downloadPdf(@RequestParam String filename) {
        try {
            String url = PYTHON_BASE + "/resources/download-pdf?filename=" + filename;
            ResponseEntity<byte[]> response = restTemplate.getForEntity(url, byte[].class);
            if (response.getBody() == null) {
                return ResponseEntity.notFound().build();
            }
            ByteArrayResource resource = new ByteArrayResource(response.getBody());
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_PDF)
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            "attachment; filename=\"" + filename + "\"")
                    .body(resource);
        } catch (Exception e) {
            log.error("下载PDF失败: filename={}", filename, e);
            return ResponseEntity.internalServerError().build();
        }
    }

    /**
     * 将 AI 生成的学习资源保存到数据库。
     * topic 优先取请求参数，为 null 时从模型返回数据中提取，最后回退为"未知主题"。
     * title 优先取模型返回的 title，回退到 topic。
     */
    private void saveResourcesToDb(Long userId, String topic, Map<String, Object> doneData) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> blocks = (List<Map<String, Object>>) doneData.get("content_blocks");
            if (blocks == null) return;

            // 确定主题：请求参数 > 模型返回 > 默认值（显式判空，getOrDefault 不防 null 值）
            String resolvedTopic = topic;
            if (resolvedTopic == null) {
                resolvedTopic = (String) doneData.get("topic");
            }
            if (resolvedTopic == null) {
                resolvedTopic = "未知主题";
            }

            for (Map<String, Object> block : blocks) {
                Resource resource = new Resource();
                resource.setUserId(userId);
                resource.setType((String) block.getOrDefault("type", "course_doc"));
                resource.setTopic(resolvedTopic);
                // title 优先使用模型返回的标题，回退到主题名
                resource.setTitle((String) block.getOrDefault("title", resolvedTopic));
                resource.setContentJson(block);
                resourceService.save(resource);
            }
            log.info("资源已保存: userId={}, topic={}, count={}", userId, resolvedTopic, blocks.size());
        } catch (Exception e) {
            log.error("保存资源失败: userId={}, topic={}", userId, topic, e);
        }
    }

    /**
     * 根据用户 ID 查询学生画像，构建传给 AI 模型的 profile 数据。
     */
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

    /**
     * 从当前登录用户上下文中获取用户 ID。
     */
    /** 资源生成后自动记录学习活动 */
    private void recordResourceActivity(Long userId) {
        try {
            LearningActivity activity = new LearningActivity()
                    .setUserId(userId)
                    .setActivityType("study")
                    .setDurationMinutes(10);
            activityService.save(activity);
        } catch (Exception e) {
            log.error("记录资源活动失败: userId={}", userId, e);
        }
    }

    private Long getUserId() {
        return UserHolder.getUser().getId();
    }
}