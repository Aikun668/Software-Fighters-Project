package com.university.learning.controller;

import com.university.learning.client.PythonClient;
import com.university.learning.common.Result;
import com.university.learning.entity.Conversation;
import com.university.learning.entity.Message;
import com.university.learning.service.IConversationService;
import com.university.learning.service.IMessageService;
import com.university.learning.utils.UserHolder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 对话会话接口
 */
@Slf4j
@RestController
@RequestMapping("/api/conversations")
@RequiredArgsConstructor
public class ConversationController {

    private final IConversationService conversationService;
    private final IMessageService messageService;
    private final PythonClient pythonClient;

    /** 创建新会话 */
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

    /** 获取会话详情 */
    @GetMapping("/{id}")
    public Result getDetail(@PathVariable Long id, @RequestParam Long userId) {
        Conversation conversation = conversationService.getById(id);
        if (conversation == null) {
            return Result.fail(404, "会话不存在");
        }
        return Result.ok(conversation);
    }

    /** 更新会话（标题、状态、摘要等） */
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

    /** 加载会话消息历史（可按mode过滤） */
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
        return Result.ok(messages);
    }

    /** 加载消息原始数据（不分mode过滤，用于压缩/摘要） */
    @GetMapping("/{id}/messages/raw")
    public Result getMessagesRaw(@PathVariable Long id,
                                 @RequestParam(defaultValue = "0") int offset,
                                 @RequestParam(defaultValue = "200") int limit) {
        List<Message> messages = messageService.listByConversationIdRaw(id, offset, limit);
        return Result.ok(messages);
    }

    /** 批量保存用户消息和AI回复 */
    @PostMapping("/{id}/messages")
    public Result saveMessages(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        String userMessage = (String) body.get("user_message");
        String assistantMessage = (String) body.get("assistant_message");
        String userMode = (String) body.getOrDefault("user_mode", "tutor");
        String assistantMode = (String) body.getOrDefault("assistant_mode", "tutor");

        int saved = messageService.saveMessages(id, userMessage, assistantMessage, userMode, assistantMode);

        // 更新会话时间
        Conversation conversation = conversationService.getById(id);
        if (conversation != null) {
            conversationService.updateById(conversation);
        }

        return Result.ok(Map.of("saved", saved));
    }

    /** 获取当前用户的会话列表 */
    @GetMapping("/mine")
    public Result listMyConversations() {
        Long userId = UserHolder.getUser().getId();
        List<Conversation> list = conversationService.listByUserId(userId);
        return Result.ok(list);
    }

    /** 删除会话 */
    @DeleteMapping("/{id}")
    public Result deleteConversation(@PathVariable Long id) {
        Long userId = UserHolder.getUser().getId();
        Conversation conversation = conversationService.getById(id);
        if (conversation == null || !conversation.getUserId().equals(userId)) {
            return Result.fail(404, "会话不存在");
        }
        // 先删消息，再删会话
        List<Message> messages = messageService.listByConversationId(id);
        for (Message msg : messages) {
            messageService.removeById(msg.getId());
        }
        conversationService.removeById(id);
        return Result.ok("删除成功");
    }

    /** 结束会话：调用AI生成摘要 + 归档 */
    @PostMapping("/{id}/end")
    public Result endConversation(@PathVariable Long id) {
        Long userId = UserHolder.getUser().getId();
        Conversation conversation = conversationService.getById(id);
        if (conversation == null || !conversation.getUserId().equals(userId)) {
            return Result.fail(404, "会话不存在");
        }

        try {
            // 调用Python AI生成会话摘要
            Map<String, Object> result = pythonClient.endConversation(id, userId, null);
            if (result != null) {
                Object summaryObj = result.get("summary");
                if (summaryObj instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> summaryMap = (Map<String, Object>) summaryObj;
                    conversation.setSummary(summaryMap.toString());
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
