package com.university.learning.service.impl;



import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.FileInfo;
import com.university.learning.mapper.FileInfoMapper;
import com.university.learning.service.IFileInfoService;
import com.university.learning.utils.MinioUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class FileInfoServiceImpl extends ServiceImpl<FileInfoMapper, FileInfo> implements IFileInfoService {

    /** content-type → 扩展名兜底表；剪贴板图片常无文件名/无后缀，需要据此补齐 */
    private static final Map<String, String> EXTENSION_BY_MIME = Map.of(
            "image/jpeg", ".jpg",
            "image/png", ".png",
            "image/webp", ".webp",
            "image/gif", ".gif",
            "image/bmp", ".bmp"
    );

    private final MinioUtil minioUtil;

    @Override
    public FileInfo uploadFile(MultipartFile file, Long userId) {
        try {
            log.info("开始上传文件: {}", file.getOriginalFilename());

            String contentType = file.getContentType();
            if (contentType == null || contentType.isBlank()) {
                contentType = "application/octet-stream";
            }
            String originalFilename = resolveOriginalFilename(file.getOriginalFilename(), contentType);

            String suffix = originalFilename.substring(originalFilename.lastIndexOf("."));
            String folder = MinioUtil.getFolderByType(contentType);
            String objectName = folder + UUID.randomUUID().toString() + suffix;

            minioUtil.uploadFile(file, objectName, contentType);

            FileInfo fileInfo = new FileInfo();
            fileInfo.setUserId(userId);
            fileInfo.setFileName(originalFilename);
            fileInfo.setFilePath(objectName);
            fileInfo.setFileSize(file.getSize());
            fileInfo.setFileType(contentType);

            this.save(fileInfo);

            log.info("文件上传成功: {}", objectName);
            return fileInfo;

        } catch (Exception e) {
            log.error("文件上传失败", e);
            throw new RuntimeException("文件上传失败: " + e.getMessage());
        }
    }

    /**
     * 归一化原始文件名，保证后续按 "." 取后缀一定安全。
     * 浏览器粘贴截图、拖拽的 blob 常常没有文件名或没有扩展名，
     * 旧实现直接抛"文件名格式错误"会让正常的剪贴板图片无法上传。
     */
    private String resolveOriginalFilename(String rawName, String contentType) {
        String fallbackExt = EXTENSION_BY_MIME.getOrDefault(
                contentType.toLowerCase(Locale.ROOT), ".bin");

        if (rawName == null || rawName.isBlank()) {
            return "pasted-image" + fallbackExt;
        }
        if (rawName.contains(".")) {
            return rawName;
        }
        return rawName + fallbackExt;
    }

    @Override
    public String getFileUrl(Long fileId) {
        FileInfo fileInfo = this.getById(fileId);
        if (fileInfo == null) {
            throw new RuntimeException("文件不存在");
        }
        return minioUtil.getFileUrl(fileInfo.getFilePath());
    }

    @Override
    public void deleteFile(Long fileId) {
        FileInfo fileInfo = this.getById(fileId);
        if (fileInfo == null) {
            throw new RuntimeException("文件不存在");
        }
        minioUtil.deleteFile(fileInfo.getFilePath());
        this.removeById(fileId);
        log.info("文件删除成功: {}", fileId);
    }
}