package com.university.learning.common;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class Result {
    private int code;
    private String message;
    private Object data;

    public static Result ok() {
        return new Result(0, "ok", null);
    }

    public static Result ok(Object data) {
        return new Result(0, "ok", data);
    }

    public static Result ok(List<?> data, Long total) {
        return new Result(0, "ok", Map.of("list", data, "total", total));
    }

    public static Result fail(String message) {
        return new Result(400, message, null);
    }

    public static Result fail(int code, String message) {
        return new Result(code, message, null);
    }
}