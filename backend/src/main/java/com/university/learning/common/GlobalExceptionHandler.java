package com.university.learning.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常处理器：兜底未在 Controller try-catch 中处理的异常，
 * 确保前端拿到的始终是统一 Result 格式而非原始 500。
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** Python AI 服务调用异常 */
    @ExceptionHandler(AIServiceException.class)
    public Result handleAIServiceException(AIServiceException e) {
        log.error("AI服务调用异常", e);
        return Result.fail(502, "AI服务暂时不可用，请稍后重试");
    }

    /** 未预期的运行时异常（代码 bug，非 AI 服务故障） */
    @ExceptionHandler(RuntimeException.class)
    public Result handleRuntimeException(RuntimeException e) {
        log.error("系统运行时异常", e);
        return Result.fail(500, "服务器内部错误");
    }

    /** 所有其他未预期异常兜底 */
    @ExceptionHandler(Exception.class)
    public Result handleException(Exception e) {
        log.error("未预期异常", e);
        return Result.fail(500, "服务器内部错误");
    }
}
