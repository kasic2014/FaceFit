package com.facefit.backend.document.repository;

import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface CareerDocumentRepository extends JpaRepository<CareerDocument, UUID> {

    @Query("""
            select d from CareerDocument d
            where d.profile.userId = :userId
              and d.deletedAt is null
              and (:documentType is null or d.documentType = :documentType)
              and (:status is null or d.processingStatus = :status)
            """)
    Page<CareerDocument> findActiveByOwner(
            @Param("userId") UUID userId,
            @Param("documentType") CareerDocumentType documentType,
            @Param("status") DocumentProcessingStatus status,
            Pageable pageable
    );

    Optional<CareerDocument> findByDocumentIdAndProfile_UserIdAndDeletedAtIsNull(
            UUID documentId,
            UUID userId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select d from CareerDocument d
            where d.documentId = :documentId
              and d.profile.userId = :userId
              and d.deletedAt is null
            """)
    Optional<CareerDocument> findActiveOwnedByIdForUpdate(
            @Param("documentId") UUID documentId,
            @Param("userId") UUID userId
    );
}
