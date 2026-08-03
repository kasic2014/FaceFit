package com.facefit.backend.common.exception;

public class InvalidDocumentFileException extends RuntimeException {

    public InvalidDocumentFileException(String message) {
        super(message);
    }

    public InvalidDocumentFileException(String message, Throwable cause) {
        super(message, cause);
    }
}
