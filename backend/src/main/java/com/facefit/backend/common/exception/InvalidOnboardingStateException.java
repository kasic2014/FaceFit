package com.facefit.backend.common.exception;

public class InvalidOnboardingStateException extends RuntimeException {

    public InvalidOnboardingStateException() {
        super("온보딩 상태 데이터가 올바르지 않습니다.");
    }
}
