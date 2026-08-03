package com.facefit.backend.common.exception;

import com.facefit.backend.common.api.ApiErrorResponse;
import jakarta.validation.ConstraintViolationException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import jakarta.servlet.http.HttpServletRequest;

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

    @ExceptionHandler(OnboardingRequiredException.class)
    public ResponseEntity<ApiErrorResponse> handleOnboardingRequired(OnboardingRequiredException exception) {
        return ResponseEntity
                .status(HttpStatus.FORBIDDEN)
                .body(ApiErrorResponse.of("ONBOARDING_REQUIRED", exception.getMessage()));
    }

    @ExceptionHandler(InvalidOnboardingStateException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidOnboardingState() {
        log.error("Invalid onboarding state detected");
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiErrorResponse.of(
                        "ONBOARDING_STATE_INVALID",
                        "온보딩 상태를 처리할 수 없습니다."
                ));
    }

    @ExceptionHandler(LegalDocumentNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleLegalDocumentNotFound(
            LegalDocumentNotFoundException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(ApiErrorResponse.of("LEGAL_DOCUMENT_NOT_FOUND", exception.getMessage()));
    }

    @ExceptionHandler(InvalidLegalActionsException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidLegalActions(
            InvalidLegalActionsException exception
    ) {
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("INVALID_LEGAL_ACTIONS", exception.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiErrorResponse> handleIllegalArgument(
            IllegalArgumentException exception
    ) {
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("INVALID_REQUEST", exception.getMessage()));
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

    @ExceptionHandler({
            HttpMessageNotReadableException.class,
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestPartException.class
    })
    public ResponseEntity<ApiErrorResponse> handleMalformedRequest(Exception exception) {
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of(
                        "INVALID_REQUEST",
                        "요청 형식이나 값이 올바르지 않습니다."
                ));
    }

    @ExceptionHandler(InvalidDocumentFileException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidDocumentFile(
            InvalidDocumentFileException exception
    ) {
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("INVALID_DOCUMENT_FILE", exception.getMessage()));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiErrorResponse> handleMaxUploadSizeExceeded(
            HttpServletRequest request
    ) {
        if (request.getRequestURI().matches(
                "^/api/v1/interview-sessions/[^/]+/answers$"
        )) {
            return ResponseEntity
                    .badRequest()
                    .body(ApiErrorResponse.of(
                            "INVALID_ANSWER_MEDIA",
                            "답변 영상은 200MB 이하여야 합니다."
                    ));
        }
        if (request.getRequestURI().startsWith("/api/v1/job-postings")) {
            return ResponseEntity
                    .status(HttpStatus.PAYLOAD_TOO_LARGE)
                    .body(ApiErrorResponse.of(
                            "FILE_TOO_LARGE",
                            "파일은 10MB 이하여야 합니다."
                    ));
        }
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of(
                        "INVALID_DOCUMENT_FILE",
                        "파일은 10MB 이하여야 합니다."
                ));
    }

    @ExceptionHandler(InterviewProgressException.class)
    public ResponseEntity<ApiErrorResponse> handleInterviewProgress(
            InterviewProgressException exception
    ) {
        return ResponseEntity
                .status(exception.getStatus())
                .body(ApiErrorResponse.of(
                        exception.getErrorCode(),
                        exception.getMessage(),
                        List.of(),
                        exception.getRetryable()
                ));
    }

    @ExceptionHandler(JobPostingFileException.class)
    public ResponseEntity<ApiErrorResponse> handleJobPostingFile(
            JobPostingFileException exception
    ) {
        return ResponseEntity
                .status(exception.getStatus())
                .body(ApiErrorResponse.of(exception.getErrorCode(), exception.getMessage()));
    }

    @ExceptionHandler(UnsupportedInputTypeException.class)
    public ResponseEntity<ApiErrorResponse> handleUnsupportedInputType(
            UnsupportedInputTypeException exception
    ) {
        return ResponseEntity
                .badRequest()
                .body(ApiErrorResponse.of("UNSUPPORTED_INPUT_TYPE", exception.getMessage()));
    }

    @ExceptionHandler(ResourceNotReadyException.class)
    public ResponseEntity<ApiErrorResponse> handleResourceNotReady(
            ResourceNotReadyException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(ApiErrorResponse.of("RESOURCE_NOT_READY", exception.getMessage()));
    }

    @ExceptionHandler(InvalidJobPostingStateException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidJobPostingState(
            InvalidJobPostingStateException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(ApiErrorResponse.of("INVALID_STATE", exception.getMessage()));
    }

    @ExceptionHandler(InvalidInterviewSessionStateException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidInterviewSessionState(
            InvalidInterviewSessionStateException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(ApiErrorResponse.of("INVALID_STATE", exception.getMessage()));
    }

    @ExceptionHandler(InvalidSessionResourceException.class)
    public ResponseEntity<ApiErrorResponse> handleInvalidSessionResource(
            InvalidSessionResourceException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(ApiErrorResponse.of("INVALID_SESSION_RESOURCE", exception.getMessage()));
    }

    @ExceptionHandler(ResourceInUseException.class)
    public ResponseEntity<ApiErrorResponse> handleResourceInUse(
            ResourceInUseException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(ApiErrorResponse.of("RESOURCE_IN_USE", exception.getMessage()));
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiErrorResponse> handleUnsupportedMediaType() {
        return ResponseEntity
                .status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
                .body(ApiErrorResponse.of(
                        "UNSUPPORTED_MEDIA_TYPE",
                        "지원하지 않는 Content-Type입니다."
                ));
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleResourceNotFound(
            ResourceNotFoundException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(ApiErrorResponse.of("RESOURCE_NOT_FOUND", exception.getMessage()));
    }

    @ExceptionHandler(StorageOperationException.class)
    public ResponseEntity<ApiErrorResponse> handleStorageOperation() {
        return ResponseEntity
                .status(HttpStatus.BAD_GATEWAY)
                .body(ApiErrorResponse.of(
                        "STORAGE_OPERATION_FAILED",
                        "파일 저장소 작업을 완료할 수 없습니다."
                ));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleUnexpected(Exception exception) {
        log.error("Unhandled exception type={}", exception.getClass().getSimpleName());
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiErrorResponse.of(
                        "INTERNAL_SERVER_ERROR",
                        "서버 내부 오류가 발생했습니다."
                ));
    }
}
