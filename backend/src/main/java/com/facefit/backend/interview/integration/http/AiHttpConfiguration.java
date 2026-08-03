package com.facefit.backend.interview.integration.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.http.HttpClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AiHttpProperties.class)
public class AiHttpConfiguration {

    @Bean
    AiHttpTransport aiHttpTransport(AiHttpProperties properties) {
        properties.requireValidTimeouts();
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(properties.getConnectTimeout())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        return new JdkAiHttpTransport(client);
    }

    @Bean
    FaceFitAiHttpClient faceFitAiHttpClient(
            AiHttpProperties properties,
            ObjectMapper objectMapper,
            AiHttpTransport transport
    ) {
        return new FaceFitAiHttpClient(
                properties,
                objectMapper,
                transport
        );
    }
}
