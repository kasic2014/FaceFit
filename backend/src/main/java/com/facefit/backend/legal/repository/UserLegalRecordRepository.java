package com.facefit.backend.legal.repository;

import com.facefit.backend.legal.domain.LegalRecordActionType;
import com.facefit.backend.legal.domain.UserLegalRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface UserLegalRecordRepository extends JpaRepository<UserLegalRecord, UUID> {

    List<UserLegalRecord>
    findAllByProfile_UserIdAndLegalDocument_LegalDocumentIdOrderByRecordedAtDesc(
            UUID userId,
            UUID legalDocumentId
    );

    boolean existsByProfile_UserIdAndLegalDocument_LegalDocumentIdAndActionType(
            UUID userId,
            UUID legalDocumentId,
            LegalRecordActionType actionType
    );
}
