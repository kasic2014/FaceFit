package com.facefit.backend.legal.repository;

import com.facefit.backend.legal.domain.LegalDocument;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface LegalDocumentRepository extends JpaRepository<LegalDocument, UUID> {

    List<LegalDocument>
    findAllByIsOnboardingRequiredTrueAndIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
            OffsetDateTime effectiveAt
    );

    List<LegalDocument> findAllByIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
            OffsetDateTime effectiveAt
    );

    List<LegalDocument>
    findAllByDocumentTypeAndIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
            String documentType,
            OffsetDateTime effectiveAt
    );

    Optional<LegalDocument>
    findByLegalDocumentIdAndIsCurrentTrueAndEffectiveAtLessThanEqual(
            UUID legalDocumentId,
            OffsetDateTime effectiveAt
    );
}
