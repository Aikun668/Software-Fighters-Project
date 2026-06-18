package com.university.university.learning.mapper;


import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.university.learning.entity.FileInfo;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface FileInfoMapper extends BaseMapper<FileInfo> {
}