package com.university.learning.controller;

import com.university.learning.common.Result;
import com.university.learning.entity.FileInfo;
import com.university.learning.service.IFileInfoService;
import com.university.learning.utils.UserHolder;
import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/file")
@RequiredArgsConstructor
public class FileController {

    private final IFileInfoService fileInfoService;

    /**
     * 上传文件到 MinIO，返回 fileId + 预签名 URL。
     * 前端拿到 url 后可直接放入 /api/chat 的 images 数组。
     */
    @Operation(summary = "上传文件", description = "上传文件到 MinIO，返回 fileId + 预签名 URL（有效期7天），建议前端拿 url 放入 chat/images")
    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Result uploadFile(@RequestParam("file") MultipartFile file) {
        try {
            Long userId = UserHolder.getUser().getId();
            FileInfo fileInfo = fileInfoService.uploadFile(file, userId);

            // 生成 MinIO 预签名 URL，前端可直接用于 chat/images
            String presignedUrl = fileInfoService.getFileUrl(fileInfo.getId());

            Map<String, Object> data = new HashMap<>();
            data.put("fileId", fileInfo.getId());
            data.put("url", presignedUrl);
            data.put("fileName", fileInfo.getFilePath());
            data.put("originalName", fileInfo.getFileName());

            return Result.ok(data);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @Operation(summary = "获取文件访问 URL", description = "返回 MinIO 预签名 URL，有效期 7 天")
    @GetMapping("/url/{fileId}")
    public Result getUrl(@PathVariable Long fileId) {
        try {
            String url = fileInfoService.getFileUrl(fileId);
            return Result.ok(url);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @Operation(summary = "删除文件", description = "同时删除 MinIO 存储和数据库记录")
    @DeleteMapping("/{fileId}")
    public Result delete(@PathVariable Long fileId) {
        try {
            fileInfoService.deleteFile(fileId);
            return Result.ok("删除成功");
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }
}
