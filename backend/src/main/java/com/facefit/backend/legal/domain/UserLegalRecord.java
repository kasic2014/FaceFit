package com.facefit.backend.legal.domain;

import com.facefit.backend.member.domain.Profile;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.DynamicInsert;
import org.hibernate.annotations.Generated;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.generator.EventType;
import org.hibernate.type.SqlTypes;

import java.net.InetAddress;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@DynamicInsert
@Table(name = "user_legal_records")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserLegalRecord {

    @Id
    @Generated
    @ColumnDefault("gen_random_uuid()")
    @Column(name = "legal_record_id", nullable = false, updatable = false)
    private UUID legalRecordId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "legal_document_id", nullable = false, updatable = false)
    private LegalDocument legalDocument;

    @Enumerated(EnumType.STRING)
    @Column(name = "action_type", nullable = false, length = 20)
    private LegalRecordActionType actionType;

    @Generated(event = EventType.INSERT)
    @ColumnDefault("now()")
    @Column(name = "recorded_at", nullable = false, updatable = false)
    private OffsetDateTime recordedAt;

    @ColumnDefault("'WEB_CHECKBOX'")
    @Column(name = "collection_method", nullable = false, length = 30)
    private String collectionMethod;

    @JdbcTypeCode(SqlTypes.INET)
    @Column(name = "ip_address", columnDefinition = "INET")
    private InetAddress ipAddress;

    @Column(name = "user_agent", columnDefinition = "TEXT")
    private String userAgent;

    private UserLegalRecord(
            Profile profile,
            LegalDocument legalDocument,
            LegalRecordActionType actionType,
            String collectionMethod,
            InetAddress ipAddress,
            String userAgent
    ) {
        this.profile = Objects.requireNonNull(profile, "profile must not be null");
        this.legalDocument = Objects.requireNonNull(legalDocument, "legalDocument must not be null");
        this.actionType = Objects.requireNonNull(actionType, "actionType must not be null");
        this.collectionMethod = collectionMethod;
        this.ipAddress = ipAddress;
        this.userAgent = userAgent;
    }

    public static UserLegalRecord create(
            Profile profile,
            LegalDocument legalDocument,
            LegalRecordActionType actionType,
            String collectionMethod,
            InetAddress ipAddress,
            String userAgent
    ) {
        return new UserLegalRecord(
                profile,
                legalDocument,
                actionType,
                collectionMethod,
                ipAddress,
                userAgent
        );
    }
}
