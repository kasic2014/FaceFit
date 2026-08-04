package com.facefit.backend.interview.storage;

import com.facefit.backend.interview.domain.StorageProvider;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.nio.file.Path;

@Component
@ConfigurationProperties(prefix = "facefit.storage.interview-answers")
public class InterviewAnswerStorageProperties {

    private StorageProvider provider = StorageProvider.NCLOUD;
    private String bucket = "facefit-interview-videos";
    private int presignedGetTtlSeconds = 300;
    private Path tempDirectory = Path.of(System.getProperty("java.io.tmpdir"), "facefit-answers");

    public StorageProvider getProvider() { return provider; }
    public void setProvider(StorageProvider provider) { this.provider = provider; }
    public String getBucket() { return bucket; }
    public void setBucket(String bucket) { this.bucket = bucket; }
    public int getPresignedGetTtlSeconds() { return presignedGetTtlSeconds; }
    public void setPresignedGetTtlSeconds(int value) { this.presignedGetTtlSeconds = value; }
    public Path getTempDirectory() { return tempDirectory; }
    public void setTempDirectory(Path tempDirectory) { this.tempDirectory = tempDirectory; }
}
