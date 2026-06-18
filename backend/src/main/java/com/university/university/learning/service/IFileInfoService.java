package com.university.university.learning.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.university.learning.entity.FileInfo;
import org.springframework.web.multipart.MultipartFile;

public interface IFileInfoService extends IService<FileInfo> {

    /**
     * 上传文件
     */
    FileInfo uploadFile(MultipartFile file, Long userId);

    /**
     * 获取文件URL
     */
    String getFileUrl(Long fileId);

    /**
     * 删除文件
     */
    void deleteFile(Long fileId);
}