package com.facefit.backend.common.exception;

public class ResourceInUseException extends RuntimeException {

    public ResourceInUseException() {
        super("진행 중인 면접 세션에서 사용하는 리소스는 삭제할 수 없습니다.");
    }
}
