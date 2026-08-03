package com.facefit.backend.legal.application;

import com.facefit.backend.common.exception.LegalDocumentNotFoundException;
import com.facefit.backend.legal.domain.LegalDocument;
import com.facefit.backend.legal.repository.LegalDocumentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class LegalDocumentService {

    private final LegalDocumentRepository legalDocumentRepository;

    @Transactional(readOnly = true)
    public List<LegalDocument> findCurrentDocuments(String type) {
        OffsetDateTime now = OffsetDateTime.now();
        if (type == null) {
            return legalDocumentRepository
                    .findAllByIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(now);
        }
        if (type.isBlank() || type.length() > 40) {
            throw new IllegalArgumentException("법률 문서 종류 필터가 올바르지 않습니다.");
        }
        return legalDocumentRepository
                .findAllByDocumentTypeAndIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
                        type,
                        now
                );
    }

    @Transactional(readOnly = true)
    public LegalDocument findCurrentDocument(UUID documentId) {
        return legalDocumentRepository
                .findByLegalDocumentIdAndIsCurrentTrueAndEffectiveAtLessThanEqual(
                        documentId,
                        OffsetDateTime.now()
                )
                .orElseThrow(LegalDocumentNotFoundException::new);
    }
}
