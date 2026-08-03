package com.facefit.backend.jobposting.ocr;

import com.facefit.backend.jobposting.application.JobProcessingException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Component
public class TesseractCommandRunner implements OcrCommandRunner {

    private static final int MAX_STDOUT_BYTES = 1_000_000;
    private static final int MAX_STDERR_BYTES = 32_000;

    private final String executable;
    private final String tessdataPrefix;

    public TesseractCommandRunner(
            @Value("${facefit.job-postings.ocr.executable:tesseract}") String executable,
            @Value("${facefit.job-postings.ocr.tessdata-prefix:}") String tessdataPrefix
    ) {
        this.executable = executable;
        this.tessdataPrefix = tessdataPrefix;
    }

    @Override
    public String run(Path inputImage, String languages, Duration timeout) {
        ProcessBuilder builder = new ProcessBuilder(List.of(
                executable,
                inputImage.toString(),
                "stdout",
                "-l",
                languages,
                "--psm",
                "6"
        ));
        if (tessdataPrefix != null && !tessdataPrefix.isBlank()) {
            builder.environment().put("TESSDATA_PREFIX", tessdataPrefix);
        }

        Process process;
        try {
            process = builder.start();
        } catch (IOException exception) {
            throw new JobProcessingException("OCR_NOT_CONFIGURED", false, exception);
        }

        try (ExecutorService streams = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<BoundedOutput> stdout = streams.submit(
                    () -> readBounded(process.getInputStream(), MAX_STDOUT_BYTES)
            );
            Future<BoundedOutput> stderr = streams.submit(
                    () -> readBounded(process.getErrorStream(), MAX_STDERR_BYTES)
            );
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new JobProcessingException("OCR_TIMEOUT", true);
            }
            BoundedOutput output = stdout.get(5, TimeUnit.SECONDS);
            stderr.get(5, TimeUnit.SECONDS);
            if (process.exitValue() != 0) {
                throw new JobProcessingException("OCR_PROCESS_FAILED", false);
            }
            if (output.truncated()) {
                throw new JobProcessingException("OCR_OUTPUT_TOO_LARGE", false);
            }
            return output.text();
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new JobProcessingException("OCR_INTERRUPTED", true, exception);
        } catch (Exception exception) {
            process.destroyForcibly();
            throw new JobProcessingException("OCR_PROCESS_FAILED", true, exception);
        }
    }

    private BoundedOutput readBounded(InputStream stream, int maxBytes) throws IOException {
        try (stream; ByteArrayOutputStream captured = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8_192];
            int read;
            int total = 0;
            boolean truncated = false;
            while ((read = stream.read(buffer)) != -1) {
                int remaining = maxBytes - total;
                if (remaining > 0) {
                    int accepted = Math.min(remaining, read);
                    captured.write(buffer, 0, accepted);
                    total += accepted;
                    if (accepted < read) {
                        truncated = true;
                    }
                } else {
                    truncated = true;
                }
            }
            return new BoundedOutput(
                    captured.toString(StandardCharsets.UTF_8),
                    truncated
            );
        }
    }

    private record BoundedOutput(String text, boolean truncated) {
    }
}
