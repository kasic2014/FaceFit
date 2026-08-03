package com.facefit.backend.jobposting.ocr;

import com.facefit.backend.jobposting.application.JobProcessingException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.UUID;

@Component
public class TesseractOcrEngine implements OcrEngine {

    private final OcrCommandRunner commandRunner;
    private final boolean enabled;
    private final String languages;
    private final Duration timeout;

    public TesseractOcrEngine(
            OcrCommandRunner commandRunner,
            @Value("${facefit.job-postings.ocr.enabled:true}") boolean enabled,
            @Value("${facefit.job-postings.ocr.languages:kor+eng}") String languages,
            @Value("${facefit.job-postings.ocr.timeout-seconds:120}") long timeoutSeconds
    ) {
        this.commandRunner = commandRunner;
        this.enabled = enabled;
        this.languages = languages;
        this.timeout = Duration.ofSeconds(timeoutSeconds);
    }

    @Override
    public String recognize(BufferedImage image) {
        if (!enabled) {
            throw new JobProcessingException("OCR_DISABLED", false);
        }
        Path temporaryDirectory = null;
        Path inputImage = null;
        try {
            temporaryDirectory = Files.createTempDirectory("facefit-ocr-" + UUID.randomUUID());
            inputImage = temporaryDirectory.resolve(UUID.randomUUID() + ".png");
            if (!ImageIO.write(image, "png", inputImage.toFile())) {
                throw new JobProcessingException("OCR_IMAGE_WRITE_FAILED", false);
            }
            return commandRunner.run(inputImage, languages, timeout);
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new JobProcessingException("OCR_TEMPORARY_FILE_FAILED", true, exception);
        } finally {
            deleteQuietly(inputImage);
            deleteQuietly(temporaryDirectory);
        }
    }

    private void deleteQuietly(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Temporary path contains no user-controlled name and is best-effort cleaned.
        }
    }
}
