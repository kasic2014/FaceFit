package com.facefit.backend.interview.storage;

import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.checksums.ResponseChecksumValidation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration
public class NcloudObjectStorageConfiguration {

    @Bean(destroyMethod = "close")
    S3Client ncloudS3Client(NcloudObjectStorageProperties properties) {
        return S3Client.builder()
    endpointOverride(properties.getEndpoint())
    region(Region.of(properties.getRegion()))
    credentialsProvider(credentials(properties))
    serviceConfiguration(S3Configuration.builder()
        pathStyleAccessEnabled(true)
        build())
    requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED)
    responseChecksumValidation(ResponseChecksumValidation.WHEN_REQUIRED)
    build();
    }

    @Bean(destroyMethod = "close")
    S3Presigner ncloudS3Presigner(NcloudObjectStorageProperties properties) {
        return S3Presigner.builder()
                .endpointOverride(properties.getEndpoint())
                .region(Region.of(properties.getRegion()))
                .credentialsProvider(credentials(properties))
                .serviceConfiguration(s3Configuration())
                .build();
    }

    private StaticCredentialsProvider credentials(NcloudObjectStorageProperties properties) {
        String accessKey = properties.configured() ? properties.getAccessKey() : "not-configured";
        String secretKey = properties.configured() ? properties.getSecretKey() : "not-configured";
        return StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey));
    }

    private S3Configuration s3Configuration() {
        return S3Configuration.builder()
                .pathStyleAccessEnabled(true)
                .checksumValidationEnabled(false)
                .build();
    }
}
