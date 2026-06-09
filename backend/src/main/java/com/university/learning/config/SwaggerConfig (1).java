package com.university.learning.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new io.swagger.v3.oas.models.info.Info()
                        .title("Learning 接口文档")
                        .version("1.0.0")
                        .description("需要在请求头中添加 Authorization: Bearer {token}"))
                .addSecurityItem(new SecurityRequirement().addList("Bearer"))
                .components(new io.swagger.v3.oas.models.Components()
                        .addSecuritySchemes("Bearer",
                                new SecurityScheme()
                                        .name("Authorization")
                                        .type(SecurityScheme.Type.HTTP)
                                        .scheme("bearer")
                                        .bearerFormat("JWT")
                                        .in(SecurityScheme.In.HEADER)));
    }
}