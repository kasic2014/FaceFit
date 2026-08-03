package com.facefit.backend.common.exception;

public class MemberAccessDeniedException extends RuntimeException {

    public MemberAccessDeniedException() {
        super("ACTIVE 상태의 회원만 접근할 수 있습니다.");
    }
}
