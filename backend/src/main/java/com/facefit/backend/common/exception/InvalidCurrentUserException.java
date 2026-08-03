package com.facefit.backend.common.exception;

public class InvalidCurrentUserException extends RuntimeException {

    public InvalidCurrentUserException(String message) {
        super(message);
    }
}
