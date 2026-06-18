package com.university.learning.common;

/**
 * Python AI 服务调用异常 — 用于 GlobalExceptionHandler 精确匹配，
 * 避免把代码 bug（NPE 等）误报为 AI 服务故障。
 */
public class AIServiceException extends RuntimeException {
    public AIServiceException(String message) {
        super(message);
    }

    public AIServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
