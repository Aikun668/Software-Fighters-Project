package com.university.university.learning;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.university.learning.mapper")
public class LearningPlatformApplication {

    public static void main(String[] args) {
        SpringApplication.run(LearningPlatformApplication.class, args);
    }

}
