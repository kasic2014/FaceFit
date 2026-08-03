package com.facefit.backend.common.exception;

import lombok.Getter;
import org.springframework.http.HttpStatus;

@Getter
public class InterviewProgressException extends RuntimeException {

    private final HttpStatus status;
    private final String errorCode;
    private final Boolean retryable;

    public InterviewProgressException(
            HttpStatus status,
            String errorCode,
            String message
    ) {
        this(status, errorCode, message, null);
    }

    public InterviewProgressException(
            HttpStatus status,
            String errorCode,
            String message,
            Boolean retryable
    ) {
        super(message);
        this.status = status;
        this.errorCode = errorCode;
        this.retryable = retryable;
    }
}
