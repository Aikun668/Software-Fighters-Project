package com.university.learning.utils;


import com.university.learning.config.MinioConfig;
import io.minio.*;
import io.minio.http.Method;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.util.concurrent.TimeUnit;

@Slf4j
@Component
@RequiredArgsConstructor
public class MinioUtil {

    private final MinioClient minioClient;
    private final MinioConfig minioConfig;

    /**
     * 初始化Bucket
     */
    public void createBucket() {
        try {
            String bucketName = minioConfig.getBucketName();
            boolean exists = minioClient.bucketExists(
                    BucketExistsArgs.builder().bucket(bucketName).build()
            );

            if (!exists) {
                minioClient.makeBucket(
                        MakeBucketArgs.builder().bucket(bucketName).build()
                );
                log.info("Bucket {} 创建成功", bucketName);
            }
        } catch (Exception e) {
            log.error("创建Bucket失败", e);
            throw new RuntimeException("MinIO初始化失败");
        }
    }

    /**
     * 上传文件
     */
    public void uploadFile(MultipartFile file, String objectName) {
        try {
            createBucket();

            minioClient.putObject(
                    PutObjectArgs.builder()
                            .bucket(minioConfig.getBucketName())
                            .object(objectName)
                            .stream(file.getInputStream(), file.getSize(), -1)
                            .contentType(file.getContentType())
                            .build()
            );

            log.info("文件上传成功: {}", objectName);

        } catch (Exception e) {
            log.error("文件上传失败", e);
            throw new RuntimeException("文件上传失败: " + e.getMessage());
        }
    }

    /**
     * 获取文件访问URL
     */
    public String getFileUrl(String objectName) {
        try {
            return minioClient.getPresignedObjectUrl(
                    GetPresignedObjectUrlArgs.builder()
                            .bucket(minioConfig.getBucketName())
                            .object(objectName)
                            .method(Method.GET)
                            .expiry(7, TimeUnit.DAYS)
                            .build()
            );
        } catch (Exception e) {
            log.error("获取文件URL失败", e);
            throw new RuntimeException("获取文件URL失败");
        }
    }

    /**
     * 下载文件
     */
    public InputStream downloadFile(String objectName) {
        try {
            return minioClient.getObject(
                    GetObjectArgs.builder()
                            .bucket(minioConfig.getBucketName())
                            .object(objectName)
                            .build()
            );
        } catch (Exception e) {
            log.error("文件下载失败", e);
            throw new RuntimeException("文件下载失败");
        }
    }

    /**
     * 删除文件
     */
    public void deleteFile(String objectName) {
        try {
            minioClient.removeObject(
                    RemoveObjectArgs.builder()
                            .bucket(minioConfig.getBucketName())
                            .object(objectName)
                            .build()
            );
            log.info("文件删除成功: {}", objectName);
        } catch (Exception e) {
            log.error("文件删除失败", e);
            throw new RuntimeException("文件删除失败");
        }
    }

    /**
     * 根据文件类型获取存储目录
     */
    public static String getFolderByType(String contentType) {
        if (contentType == null) {
            return "files/";
        }
        if (contentType.startsWith("video")) {
            return "videos/";
        } else if (contentType.startsWith("image")) {
            return "images/";
        } else if (contentType.startsWith("audio")) {
            return "audios/";
        } else {
            return "files/";
        }
    }
}