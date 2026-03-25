package com.wildlifevn.backend.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI wildlifeOpenAPI() {
        return new OpenAPI()
                .info(
                        new Info()
                                .title("Vietnam Wildlife API")
                                .version("v1")
                                .description(
                                        "API for wildlife species library, image identification, and Vietnamese conservation QA chatbot")
                                .contact(
                                        new Contact()
                                                .name("DATN Wildlife Team")
                                                .email("you@example.com"))
                                .license(new License().name("For Academic Use")));
    }
}
