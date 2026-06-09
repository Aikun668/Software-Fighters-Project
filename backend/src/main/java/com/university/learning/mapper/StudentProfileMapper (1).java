package com.university.learning.mapper;


import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import com.university.learning.entity.StudentProfile;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface StudentProfileMapper extends BaseMapper<StudentProfile> {
}