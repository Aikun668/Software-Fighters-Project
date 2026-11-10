package com.university.learning.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.ResponseEntity;

/**
 * 全局异常处理器：兜底未在 Controller try-catch 中处理的异常，
 * 确保前端拿到的始终是统一 Result 格式而非原始 500。
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** Preserve explicit authorization/not-found HTTP statuses and the existing Result envelope. */
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Result> handleResponseStatus(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode()).body(Result.fail(e.getStatusCode().value(), e.getReason()));
    }

    /** Python AI 服务调用异常 */
    @ExceptionHandler(AIServiceException.class)
    public Result handleAIServiceException(AIServiceException e) {
        log.error("AI服务调用异常", e);
        return Result.fail(502, "AI服务暂时不可用，请稍后重试");
    }

    /**
     * 上传文件超过 multipart 上限。
     * 该异常在进入 Controller 之前由 DispatcherServlet 抛出，
     * 若不单独处理就会被下面的 RuntimeException/Exception 兜底成
     * "服务器内部错误"，前端无法得知是体积超限。
     */
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public Result handleMaxUploadSizeExceeded(MaxUploadSizeExceededException e) {
        log.warn("上传文件超过大小限制", e);
        return Result.fail(413, "文件过大，单个文件请控制在 20MB 以内");
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
