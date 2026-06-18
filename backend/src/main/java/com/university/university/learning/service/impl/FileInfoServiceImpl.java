package com.university.university.learning.service.impl;



import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.university.learning.entity.FileInfo;
import com.university.learning.mapper.FileInfoMapper;
import com.university.learning.service.IFileInfoService;
import com.university.learning.utils.MinioUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class FileInfoServiceImpl extends ServiceImpl<FileInfoMapper, FileInfo> implements IFileInfoService {

    private final MinioUtil minioUtil;

    @Override
    public FileInfo uploadFile(MultipartFile file, Long userId) {
        try {
            log.info("开始上传文件: {}", file.getOriginalFilename());

            String originalFilename = file.getOriginalFilename();
            if (originalFilename == null || !originalFilename.contains(".")) {
                throw new RuntimeException("文件名格式错误");
            }

            String suffix = originalFilename.substring(originalFilename.lastIndexOf("."));
            String folder = MinioUtil.getFolderByType(file.getContentType());
            String objectName = folder + UUID.randomUUID().toString() + suffix;

            minioUtil.uploadFile(file, objectName);

            FileInfo fileInfo = new FileInfo();
            fileInfo.setUserId(userId);
            fileInfo.setFileName(originalFilename);
            fileInfo.setFilePath(objectName);
            fileInfo.setFileSize(file.getSize());
            fileInfo.setFileType(file.getContentType());

            this.save(fileInfo);

            log.info("文件上传成功: {}", objectName);
            return fileInfo;

        } catch (Exception e) {
            log.error("文件上传失败", e);
            throw new RuntimeException("文件上传失败: " + e.getMessage());
        }
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