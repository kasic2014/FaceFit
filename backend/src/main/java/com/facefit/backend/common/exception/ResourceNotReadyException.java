package com.facefit.backend.common.exception;

public class ResourceNotReadyException extends RuntimeException {

    public ResourceNotReadyException() {
        super("처리 중인 지원공고는 수정할 수 없습니다.");
    }
}
