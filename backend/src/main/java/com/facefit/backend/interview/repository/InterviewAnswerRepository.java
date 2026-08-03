package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewAnswer;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.List;
import java.util.UUID;

public interface InterviewAnswerRepository extends JpaRepository<InterviewAnswer, UUID> {

    Optional<InterviewAnswer> findByAnswerIdAndProfile_UserId(
            UUID answerId,
            UUID userId
    );

    Optional<InterviewAnswer> findByTurn_TurnId(UUID turnId);

    List<InterviewAnswer> findAllBySession_SessionIdOrderByTurn_QuestionOrder(
            UUID sessionId
    );

    long countBySession_SessionIdAndConfirmedAtIsNotNull(UUID sessionId);

    boolean existsBySession_SessionIdAndStatus(
            UUID sessionId,
            com.facefit.backend.interview.domain.InterviewAnswerStatus status
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from InterviewAnswer a where a.answerId = :answerId")
    Optional<InterviewAnswer> findByIdForUpdate(@Param("answerId") UUID answerId);
}
