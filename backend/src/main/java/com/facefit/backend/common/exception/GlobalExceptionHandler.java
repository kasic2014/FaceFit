package com.facefit.backend.common.exception;

import com.facefit.backend.common.api.ApiErrorResponse;
import jakarta.validation.ConstraintViolationException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(InvalidCurrentUserException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidCurrentUser(InvalidCurrentUserException exception) {
        return ResponseEntity
                .status(HttpStatus.UNAUTHORIZED)
                .body(ApiErrorResponse.of("INVALID_AUTHENTICATED_USER", exception.getMessage()));
    }

    @ExceptionHandler(MemberAccessDeniedException.class)
    public ResponseEntity<ApiErrorResponse> handleMemberAccessDenied(MemberAccessDeniedException exception) {
        return ResponseEntity
                .status(HttpStatus.FORBIDDEN)
                .body(ApiErrorResponse.of("MEMBER_ACCESS_DENIED", exception.getMessage()));
    }

    @ExceptionHandler(ProfileProvisioningException.class)
    public ResponseEntity<ApiErrorResponse> handleProfileProvisioning(ProfileProvisioningException exception) {
        log.error("Current profile provisioning failed");
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiErrorResponse.of(
                        "PROFILE_PROVISIONING_FAILED",
                        "현재 사용자 프로필을 준비할 수 없습니다."
                ));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception
    ) {
        List<ApiErrorResponse.FieldViolation> details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new ApiErrorResponse.FieldViolation(
                        error.getField(),
                        error.getDefaultMessage() == null ? "유효하지 않은 값입니다." : error.getDefaultMessage()
                ))
                .toList();

        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("VALIDATION_ERROR", "입력값을 확인해주세요.", details));
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiErrorResponse> handleConstraintViolation(
            ConstraintViolationException exception
    ) {
        List<ApiErrorResponse.FieldViolation> details = exception.getConstraintViolations()
                .stream()
                .map(violation -> new ApiErrorResponse.FieldViolation(
                        violation.getPropertyPath().toString(),
                        violation.getMessage()
                ))
                .toList();

        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("VALIDATION_ERROR", "입력값을 확인해주세요.", details));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleUnexpected(Exception exception) {
        log.error("Unhandled exception", exception);
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiErrorResponse.of(
                        "INTERNAL_SERVER_ERROR",
                        "서버 내부 오류가 발생했습니다."
                ));
    }
}
