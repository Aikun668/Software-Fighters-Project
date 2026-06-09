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

    @Operation(summary = "上传文件")
    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Result uploadFile(@RequestParam("file") MultipartFile file) {
        try {

            Long userId = UserHolder.getUser().getId();

            FileInfo fileInfo = fileInfoService.uploadFile(file, userId);

            Map<String, Object> data = new HashMap<>();
            data.put("fileId", fileInfo.getId());
            data.put("fileName", fileInfo.getFilePath());
            data.put("originalName", fileInfo.getFileName());

            return Result.ok(data);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

    @GetMapping("/url/{fileId}")
    public Result getUrl(@PathVariable Long fileId) {
        try {
            String url = fileInfoService.getFileUrl(fileId);
            return Result.ok(url);
        } catch (Exception e) {
            return Result.fail(e.getMessage());
        }
    }

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