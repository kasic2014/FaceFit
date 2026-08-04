package com.facefit.backend.interview.application;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public record ValidatedAnswerMedia(
        Path path,
        String mimeType,
        String extension,
        long size,
        String sha256,
        long durationMillis
) implements AutoCloseable {

    @Override
    public void close() {
        try {
            Files.deleteIfExists(path);
            Path parent = path.getParent();
            if (parent != null) {
                Files.deleteIfExists(parent);
            }
        } catch (IOException ignored) {
            // Best effort. The isolated temp directory can be swept after restart.
        }
    }
}
