package com.facefit.backend.interview.storage;

import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

public final class StoredAnswerMedia implements AutoCloseable {

    private final InputStream inputStream;
    private final long contentLength;

    public StoredAnswerMedia(InputStream inputStream, long contentLength) {
        this.inputStream = Objects.requireNonNull(inputStream);
        this.contentLength = contentLength;
    }

    public InputStream inputStream() {
        return inputStream;
    }

    public long contentLength() {
        return contentLength;
    }

    @Override
    public void close() throws IOException {
        inputStream.close();
    }
}
