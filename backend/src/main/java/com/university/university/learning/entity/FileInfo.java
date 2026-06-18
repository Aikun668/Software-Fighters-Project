package com.university.university.learning.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("file_info")
public class FileInfo {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;
    private String fileName;      // 原始文件名
    private String filePath;      // MinIO存储路径
    private Long fileSize;        // 文件大小
    private String fileType;      // 文件类型

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}