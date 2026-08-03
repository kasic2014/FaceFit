package com.facefit.backend.jobposting.application;

public class JobProcessingException extends RuntimeException {

    private final String errorCode;
    private final boolean retryable;

    public JobProcessingException(String errorCode, boolean retryable) {
        super(errorCode);
        this.errorCode = errorCode;
        this.retryable = retryable;
    }

    public JobProcessingException(String errorCode, boolean retryable, Throwable cause) {
        super(errorCode, cause);
        this.errorCode = errorCode;
        this.retryable = retryable;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public boolean isRetryable() {
        return retryable;
    }
}
