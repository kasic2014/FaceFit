package com.facefit.backend.interview.integration;

public sealed interface PortResult<T>
        permits PortResult.Success, PortResult.RetryableFailure, PortResult.PermanentFailure {

    record Success<T>(T value) implements PortResult<T> {
    }

    record RetryableFailure<T>(String errorCode) implements PortResult<T> {
    }

    record PermanentFailure<T>(String errorCode) implements PortResult<T> {
    }

    static <T> PortResult<T> success(T value) {
        return new Success<>(value);
    }

    static <T> PortResult<T> retryableFailure(String errorCode) {
        return new RetryableFailure<>(errorCode);
    }

    static <T> PortResult<T> permanentFailure(String errorCode) {
        return new PermanentFailure<>(errorCode);
    }
}
