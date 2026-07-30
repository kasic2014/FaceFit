package com.facefit.backend.common.exception;

public class OnboardingRequiredException extends RuntimeException {

    public OnboardingRequiredException() {
        super("서비스를 이용하려면 온보딩을 완료해야 합니다.");
    }
}
