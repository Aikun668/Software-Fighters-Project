package com.university.learning.utils;


import cn.hutool.core.util.StrUtil;
import org.springframework.web.multipart.MultipartFile;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

/**
 * 文件工具类
 */
public class FileUtils {

    // 允许的图片类型
    private static final List<String> IMAGE_TYPES = Arrays.asList(
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"
    );

    // 允许的文档类型
    private static final List<String> DOCUMENT_TYPES = Arrays.asList(
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    );

    // 允许的视频类型
    private static final List<String> VIDEO_TYPES = Arrays.asList(
            "video/mp4", "video/webm", "video/ogg", "video/quicktime"
    );

    // 允许的音频类型
    private static final List<String> AUDIO_TYPES = Arrays.asList(
            "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4"
    );

    // 文件大小限制: 100MB
    public static final long MAX_FILE_SIZE = 100 * 1024 * 1024;

    /**
     * 校验文件类型
     */
    public static boolean isAllowedFileType(String contentType) {
        return IMAGE_TYPES.contains(contentType)
                || DOCUMENT_TYPES.contains(contentType)
                || VIDEO_TYPES.contains(contentType)
                || AUDIO_TYPES.contains(contentType);
    }

    /**
     * 获取文件类型分类
     */
    public static String getFileCategory(String contentType) {
        if (StrUtil.isBlank(contentType)) return "other";
        if (IMAGE_TYPES.contains(contentType)) return "image";
        if (VIDEO_TYPES.contains(contentType)) return "video";
        if (AUDIO_TYPES.contains(contentType)) return "audio";
        if (DOCUMENT_TYPES.contains(contentType)) return "document";
        return "other";
    }

    /**
     * 生成唯一文件名（保留原扩展名）
     */
    public static String generateFileName(String originalFilename) {
        String ext = "";
        if (StrUtil.isNotBlank(originalFilename) && originalFilename.contains(".")) {
            ext = originalFilename.substring(originalFilename.lastIndexOf("."));
        }
        return UUID.randomUUID().toString().replace("-", "") + ext;
    }

    /**
     * 根据文件分类和文件名生成存储路径
     * 格式: category/yyyy-MM/uuid_filename
     */
    public static String generatePath(String category, String filename) {
        return category + "/" + java.time.LocalDate.now() + "/" + filename;
    }
}