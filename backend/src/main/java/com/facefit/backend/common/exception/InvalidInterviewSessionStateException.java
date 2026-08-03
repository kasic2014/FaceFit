package com.facefit.backend.common.exception;

public class InvalidInterviewSessionStateException extends RuntimeException {

    public InvalidInterviewSessionStateException() {
        super("현재 면접 세션 상태에서는 요청을 처리할 수 없습니다.");
    }

    public InvalidInterviewSessionStateException(String message) {
        super(message);
    }
}
