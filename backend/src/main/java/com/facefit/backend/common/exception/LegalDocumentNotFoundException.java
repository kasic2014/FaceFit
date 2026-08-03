package com.facefit.backend.common.exception;

public class LegalDocumentNotFoundException extends RuntimeException {

    public LegalDocumentNotFoundException() {
        super("현재 제공 가능한 법률 문서를 찾을 수 없습니다.");
    }
}
