package com.university.learning.controller;

import com.university.learning.client.PythonClient;

import com.university.learning.entity.Resource;
import com.university.learning.service.IResourceService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
public class ChatController {

    private final PythonClient pythonClient;
    private final IResourceService resourceService;

    /**
     * 统一对话入口
     * 前端传纯字符串: "给我出5道反向传播的选择题"
     */
    @PostMapping
    public SseEmitter chat(@RequestBody String message) {
        Long userId = getUserId();
        log.info("统一对话: userId={}, message={}", userId, message);

        return pythonClient.unifiedChatStream(userId, message, (doneData) -> {
            saveResultIfNeeded(userId, doneData);
        });
    }

    private void saveResultIfNeeded(Long userId, Map<String, Object> doneData) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> contentBlocks = (List<Map<String, Object>>) doneData.get("content_blocks");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> questions = (List<Map<String, Object>>) doneData.get("questions");
            String topic = (String) doneData.getOrDefault("topic", "未知主题");

            if (contentBlocks != null && !contentBlocks.isEmpty()) {
                for (Map<String, Object> block : contentBlocks) {
                    Resource resource = new Resource();
                    resource.setUserId(userId);
                    resource.setType((String) block.getOrDefault("type", "course_doc"));
                    resource.setTopic(topic);
                    resource.setContentJson(block);
                    resourceService.save(resource);
                }
                log.info("资源已保存: userId={}, count={}", userId, contentBlocks.size());
            }

            if (questions != null && !questions.isEmpty()) {
                Resource resource = new Resource();
                resource.setUserId(userId);
                resource.setType("exercise");
                resource.setTopic(topic);
                Map<String, Object> contentJson = new HashMap<>();
                contentJson.put("questions", questions);
                contentJson.put("count", questions.size());
                resource.setContentJson(contentJson);
                resourceService.save(resource);
                log.info("练习题已保存: userId={}, count={}", userId, questions.size());
            }
        } catch (Exception e) {
            log.error("存库失败: userId={}", userId, e);
        }
    }

    private Long getUserId() {
        return UserHolder.getUser().getId();

    }
}