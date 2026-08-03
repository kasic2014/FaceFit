package com.facefit.backend.common.exception;

public class ProfileProvisioningException extends RuntimeException {

    public ProfileProvisioningException() {
        super("현재 사용자 프로필을 준비할 수 없습니다.");
    }

    public ProfileProvisioningException(Throwable cause) {
        super("현재 사용자 프로필을 준비할 수 없습니다.", cause);
    }
}
