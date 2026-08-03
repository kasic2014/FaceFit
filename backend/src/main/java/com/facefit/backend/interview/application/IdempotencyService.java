package com.facefit.backend.interview.application;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.interview.domain.ApiIdempotencyRecord;
import com.facefit.backend.interview.domain.IdempotencyProcessingStatus;
import com.facefit.backend.interview.repository.ApiIdempotencyRecordRepository;
import com.facefit.backend.member.domain.Profile;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
@RequiredArgsConstructor
public class IdempotencyService {

    private static final Pattern KEY_PATTERN =
            Pattern.compile("^[A-Za-z0-9._:-]{8,64}$");

    private final ApiIdempotencyRecordRepository repository;
    private final ObjectMapper objectMapper;

    public String requireValidKey(String key) {
        if (key == null || key.isBlank()) {
            throw new InterviewProgressException(
                    HttpStatus.BAD_REQUEST,
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "Idempotency-Key 헤더가 필요합니다."
            );
        }
        if (!KEY_PATTERN.matcher(key).matches()) {
            throw new InterviewProgressException(
                    HttpStatus.BAD_REQUEST,
                    "INVALID_IDEMPOTENCY_KEY",
                    "Idempotency-Key 형식이 올바르지 않습니다."
            );
        }
        return key;
    }

    public String requestHash(String canonicalRequest) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(
                            canonicalRequest.getBytes(StandardCharsets.UTF_8)
                    )
            );
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", impossible);
        }
    }

    public BeginResult begin(
            Profile profile,
            String method,
            String uri,
            String key,
            String requestHash
    ) {
        ApiIdempotencyRecord existing = repository.findForUpdate(
                profile.getUserId(),
                method,
                uri,
                key
        ).orElse(null);
        if (existing == null) {
            ApiIdempotencyRecord created = repository.saveAndFlush(
                    ApiIdempotencyRecord.start(
                            UUID.randomUUID(),
                            profile,
                            method,
                            uri,
                            key,
                            requestHash
                    )
            );
            return BeginResult.started(created);
        }
        if (!existing.getRequestHash().equals(requestHash)) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "같은 Idempotency-Key를 다른 요청에 사용할 수 없습니다."
            );
        }
        if (existing.getStatus() == IdempotencyProcessingStatus.PROCESSING) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    "동일한 요청이 처리 중입니다."
            );
        }
        return BeginResult.replay(
                existing,
                existing.getResponseHttpStatus(),
                existing.getResponseBody()
        );
    }

    public void complete(
            ApiIdempotencyRecord record,
            int httpStatus,
            Object response
    ) {
        try {
            record.complete(httpStatus, objectMapper.writeValueAsString(response));
            repository.saveAndFlush(record);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("멱등성 응답을 저장할 수 없습니다.", exception);
        }
    }

    public ApiIdempotencyRecord findForUpdate(UUID recordId) {
        return repository.findByIdForUpdate(recordId)
                .orElseThrow(() -> new IllegalStateException(
                        "멱등성 처리 레코드를 찾을 수 없습니다."
                ));
    }

    public <T> T readResponse(String body, Class<T> responseType) {
        try {
            return objectMapper.readerFor(responseType)
                    .without(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
                    .readValue(body);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("저장된 멱등성 응답을 읽을 수 없습니다.", exception);
        }
    }

    public void delete(UUID recordId) {
        repository.deleteById(recordId);
        repository.flush();
    }

    public record BeginResult(
            ApiIdempotencyRecord record,
            boolean replay,
            Integer responseStatus,
            String responseBody
    ) {
        static BeginResult started(ApiIdempotencyRecord record) {
            return new BeginResult(record, false, null, null);
        }

        static BeginResult replay(
                ApiIdempotencyRecord record,
                int status,
                String body
        ) {
            return new BeginResult(record, true, status, body);
        }
    }
}
