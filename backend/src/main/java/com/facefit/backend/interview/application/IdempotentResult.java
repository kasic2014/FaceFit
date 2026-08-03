package com.facefit.backend.interview.application;

public record IdempotentResult<T>(
        int httpStatus,
        T body
) {
}
