package com.university.learning.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * PPTX/PDF 导出请求 DTO
 */
@Data
public class ExportRequest {
    /** 内容块列表 */
    private List<Map<String, Object>> content_blocks;
    /** 导出标题 */
    private String title;
}
