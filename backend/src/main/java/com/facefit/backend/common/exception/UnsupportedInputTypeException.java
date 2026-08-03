package com.facefit.backend.common.exception;

public class UnsupportedInputTypeException extends RuntimeException {

    public UnsupportedInputTypeException() {
        super("요청 Content-Type과 inputType이 일치하지 않습니다.");
    }
}
