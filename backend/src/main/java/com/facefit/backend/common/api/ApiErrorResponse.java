package com.facefit.backend.common.api;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;
import java.util.List;

public record ApiErrorResponse(
        boolean success,
        ErrorBody error,
        Instant timestamp
) {

    public static ApiErrorResponse of(String code, String message) {
        return of(code, message, List.of());
    }

    public static ApiErrorResponse of(String code, String message, List<FieldViolation> details) {
        return new ApiErrorResponse(
                false,
                new ErrorBody(code, message, details),
                Instant.now()
        );
    }

    public record ErrorBody(
            String code,
            String message,
            @JsonInclude(JsonInclude.Include.NON_EMPTY)
            List<FieldViolation> details
    ) {
    }

    public record FieldViolation(
            String field,
            String message
    ) {
    }
}
