package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.ApiIdempotencyRecord;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface ApiIdempotencyRecordRepository
        extends JpaRepository<ApiIdempotencyRecord, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from ApiIdempotencyRecord r where r.id = :id")
    Optional<ApiIdempotencyRecord> findByIdForUpdate(@Param("id") UUID id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select r from ApiIdempotencyRecord r
            where r.profile.userId = :userId
              and r.httpMethod = :httpMethod
              and r.requestUri = :requestUri
              and r.idempotencyKey = :idempotencyKey
            """)
    Optional<ApiIdempotencyRecord> findForUpdate(
            @Param("userId") UUID userId,
            @Param("httpMethod") String httpMethod,
            @Param("requestUri") String requestUri,
            @Param("idempotencyKey") String idempotencyKey
    );
}
