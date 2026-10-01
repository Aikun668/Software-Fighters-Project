package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IFileInfoService;
import com.university.learning.service.IMessageService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/conversations")
@RequiredArgsConstructor
public class ConversationController {

    private final IConversationService conversationService;
    private final IMessageService messageService;
    private final IFileInfoService fileInfoService;
    private final PythonClient pythonClient;

    @Operation(summary = "创建新会话")
    @PostMapping
    public Result create(@RequestBody Map<String, Object> body) {
        Long userId = getUserId(body);
        Conversation conversation = new Conversation()
                .setUserId(userId)
                .setTitle("新对话")
                .setStatus("active");
        conversationService.save(conversation);
        return Result.ok(conversation);
    }

    @Operation(summary = "获取会话详情")
    @GetMapping("/{id}")
    public Result getDetail(@PathVariable Long id, @RequestParam Long userId) {
        Conversation conversation = conversationService.getById(id);
        if (conversation == null) {
            return Result.fail(404, "会话不存在");
        }
        return Result.ok(conversation);
    }

    @Operation(summary = "更新会话", description = "可更新标题、状态(active/archived)、摘要")
    @PutMapping("/{id}")
    public Result update(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        Conversation conversation = conversationService.getById(id);
        if (conversation == null) {
            return Result.fail(404, "会话不存在");
        }
        if (body.containsKey("title")) conversation.setTitle((String) body.get("title"));
        if (body.containsKey("status")) conversation.setStatus((String) body.get("status"));
        if (body.containsKey("summary")) conversation.setSummary((String) body.get("summary"));
        conversationService.updateById(conversation);
        return Result.ok(conversation);
    }

    @Operation(summary = "获取会话消息列表", description = "可按 mode 过滤(tutor/path/resource/profile/chat)")
    @GetMapping("/{id}/messages")
    public Result getMessages(@PathVariable Long id,
                              @RequestParam(required = false) String mode,
                              @RequestParam(defaultValue = "50") int limit) {
        List<Message> messages;
        if (mode != null) {
            messages = messageService.listByConversationIdAndMode(id, mode, limit);
        } else {
            messages = messageService.listByConversationId(id);
        }
        attachImageUrls(messages);
        return Result.ok(messages);
    }

    @Operation(summary = "获取原始消息(分页)", description = "不分 mode 过滤，用于压缩/摘要场景")
    @GetMapping("/{id}/messages/raw")
    public Result getMessagesRaw(@PathVariable Long id,
                                 @RequestParam(defaultValue = "0") int offset,
                                 @RequestParam(defaultValue = "200") int limit) {
        List<Message> messages = messageService.listByConversationIdRaw(id, offset, limit);
        attachImageUrls(messages);
        return Result.ok(messages);
    }

    /**
     * 用落库的 imageFileIds 重新签发图片 URL。
     *
     * 数据库只存 file_info.id，不存预签名 URL（URL 7 天过期），
     * 所以每次回读都在这里重新签名，历史图片才不会失效。
     * 单个文件缺失或 MinIO 异常不影响整条消息的回读。
     */
    private void attachImageUrls(List<Message> messages) {
        for (Message message : messages) {
            List<Long> fileIds = message.getImageFileIds();
            if (fileIds == null || fileIds.isEmpty()) {
                continue;
            }
            List<String> urls = new ArrayList<>(fileIds.size());
            for (Long fileId : fileIds) {
                if (fileId == null) {
                    continue;
                }
                try {
                    urls.add(fileInfoService.getFileUrl(fileId));
                } catch (Exception e) {
                    log.warn("历史图片签名失败，跳过: messageId={}, fileId={}", message.getId(), fileId, e);
                }
            }
            message.setImages(urls);
        }
    }

    @Operation(summary = "批量保存消息", description = "手动保存用户消息和 AI 回复")
    @PostMapping("/{id}/messages")
    public Result saveMessages(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        String userMessage = (String) body.get("user_message");
        String assistantMessage = (String) body.get("assistant_message");
        String userMode = (String) body.getOrDefault("user_mode", "tutor");
        String assistantMode = (String) body.getOrDefault("assistant_mode", "tutor");

        int saved = messageService.saveMessages(id, userMessage, assistantMessage, userMode, assistantMode);

        Conversation conversation = conversationService.getById(id);
        if (conversation != null) {
            conversationService.updateById(conversation);
        }

        return Result.ok(Map.of("saved", saved));
    }

    @Operation(summary = "获取当前用户会话列表")
    @GetMapping("/mine")
    public Result listMyConversations() {
        Long userId = UserHolder.getUser().getId();
        List<Conversation> list = conversationService.listByUserId(userId);
        return Result.ok(list);
    }

    @Operation(summary = "删除会话", description = "同时删除该会话下所有消息")
    @DeleteMapping("/{id}")
    public Result deleteConversation(@PathVariable Long id) {
        Long userId = UserHolder.getUser().getId();
        Conversation conversation = conversationService.getById(id);
        if (conversation == null || !conversation.getUserId().equals(userId)) {
            return Result.fail(404, "会话不存在");
        }
        List<Message> messages = messageService.listByConversationId(id);
        for (Message msg : messages) {
            messageService.removeById(msg.getId());
        }
        conversationService.removeById(id);
        return Result.ok("删除成功");
    }

    @Operation(summary = "结束会话", description = "归档会话，标记为archived状态")
    @PostMapping("/{id}/end")
    public Result endConversation(@PathVariable Long id) {
        Long userId = UserHolder.getUser().getId();
        Conversation conversation = conversationService.getById(id);
        if (conversation == null || !conversation.getUserId().equals(userId)) {
            return Result.fail(404, "会话不存在");
        }

        // 生成会话摘要（LLM总结）
        try {
            List<Message> messages = messageService.listByConversationId(id);
            List<Map<String, Object>> msgList = messages.stream().map(m -> {
                Map<String, Object> item = new java.util.LinkedHashMap<>();
                item.put("role", m.getRole());
                item.put("content", m.getContent());
                return item;
            }).collect(java.util.stream.Collectors.toList());
            Map<String, Object> result = pythonClient.getConversationSummary(id, msgList, null);
            if (result != null) {
                Object summaryObj = result.get("summary");
                if (summaryObj != null) {
                    conversation.setSummary(summaryObj.toString());
                }
            }
        } catch (Exception e) {
            log.warn("AI摘要生成失败，继续归档: convId={}", id);
        }

        conversation.setStatus("archived");
        conversationService.updateById(conversation);
        return Result.ok(conversation);
    }

    private Long getUserId(Map<String, Object> body) {
        if (body.containsKey("user_id")) {
            return Long.valueOf(body.get("user_id").toString());
        }
        return UserHolder.getUser().getId();
    }
}
