package com.university.learning.entity;


import com.baomidou.mybatisplus.annotation.*;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName(value = "resources", autoResultMap = true)
public class Resource {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String type;        // course_doc/mind_map/exercise/reading/code_practice
    private String topic;       // 知识点名称

    private String title;       // 资源标题
    @TableField(typeHandler = JacksonTypeHandler.class)
    private Object contentJson; // 资源内容 JSON

    private String filePath;    // 文件路径

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}