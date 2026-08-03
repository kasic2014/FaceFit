package com.facefit.backend.common.exception;

import org.springframework.http.HttpStatus;

public class JobPostingFileException extends RuntimeException {

    private final HttpStatus status;
    private final String errorCode;

    private JobPostingFileException(HttpStatus status, String errorCode, String message) {
        super(message);
        this.status = status;
        this.errorCode = errorCode;
    }

    public static JobPostingFileException invalid(String message) {
        return new JobPostingFileException(HttpStatus.BAD_REQUEST, "INVALID_FILE", message);
    }

    public static JobPostingFileException tooLarge() {
        return new JobPostingFileException(
                HttpStatus.PAYLOAD_TOO_LARGE,
                "FILE_TOO_LARGE",
                "파일은 10MB 이하여야 합니다."
        );
    }

    public static JobPostingFileException unsupported(String message) {
        return new JobPostingFileException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "FILE_TYPE_NOT_SUPPORTED",
                message
        );
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
