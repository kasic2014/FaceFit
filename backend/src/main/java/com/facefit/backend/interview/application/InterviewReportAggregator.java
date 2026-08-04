package com.facefit.backend.interview.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.facefit.backend.interview.domain.InterviewAnalysisResult;
import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.ReportAxis;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Component
@RequiredArgsConstructor
public class InterviewReportAggregator {

    public static final String SCHEMA_VERSION = "1.0";
    private static final int REQUIRED_ANSWERS = 10;

    private final ObjectMapper objectMapper;

    public AggregatedReport aggregate(
            List<InterviewAnswer> answers,
            List<InterviewAnalysisResult> results
    ) {
        return aggregate(answers, results, true);
    }

    public AggregatedReport aggregate(
            List<InterviewAnswer> answers,
            List<InterviewAnalysisResult> results,
            boolean voiceAnalysisEnabled
    ) {
        int expectedResults = REQUIRED_ANSWERS * (voiceAnalysisEnabled ? 3 : 2);
        if (answers.size() != REQUIRED_ANSWERS || results.size() != expectedResults) {
            throw new IllegalArgumentException("필수 분석 결과가 완전하지 않습니다.");
        }
        Map<UUID, List<InterviewAnalysisResult>> byAnswer = results.stream()
                .collect(Collectors.groupingBy(
                        result -> result.getAnswer().getAnswerId()
                ));
        EnumMap<ReportAxis, List<BigDecimal>> scores =
                new EnumMap<>(ReportAxis.class);
        for (ReportAxis axis : ReportAxis.values()) {
            if (axis == ReportAxis.SPEECH && !voiceAnalysisEnabled) {
                continue;
            }
            scores.put(axis, new ArrayList<>());
        }
        ArrayNode questionFeedback = objectMapper.createArrayNode();
        StringBuilder canonical = new StringBuilder(SCHEMA_VERSION);

        for (InterviewAnswer answer : answers) {
            List<InterviewAnalysisResult> answerResults =
                    byAnswer.getOrDefault(answer.getAnswerId(), List.of());
            InterviewAnalysisResult cv = unique(answerResults, InterviewJobType.CV);
            InterviewAnalysisResult voice = voiceAnalysisEnabled
                    ? unique(answerResults, InterviewJobType.VOICE)
                    : null;
            InterviewAnalysisResult content = unique(
                    answerResults,
                    InterviewJobType.CONTENT
            );
            add(scores, ReportAxis.GAZE, cv.getGazeScore());
            add(scores, ReportAxis.POSTURE, cv.getPostureScore());
            if (voiceAnalysisEnabled) {
                add(scores, ReportAxis.SPEECH, voice.getSpeechScore());
            }
            add(scores, ReportAxis.CONTENT, content.getContentScore());

            ObjectNode item = objectMapper.createObjectNode();
            item.put("questionId", answer.getTurn().getTurnId().toString());
            item.put("questionOrder", answer.getTurn().getQuestionOrder());
            item.put("questionType", answer.getTurn().getQuestionType().name());
            item.put("answerId", answer.getAnswerId().toString());
            ObjectNode itemScores = item.putObject("scores");
            itemScores.put("gaze", cv.getGazeScore());
            itemScores.put("posture", cv.getPostureScore());
            if (voiceAnalysisEnabled) {
                itemScores.put("speech", voice.getSpeechScore());
            } else {
                itemScores.putNull("speech");
            }
            itemScores.put("content", content.getContentScore());
            ObjectNode feedback = item.putObject("feedback");
            feedback.set("cv", cv.getPublicFeedback().deepCopy());
            feedback.set(
                    "voice",
                    voiceAnalysisEnabled
                            ? voice.getPublicFeedback().deepCopy()
                            : objectMapper.createArrayNode()
            );
            feedback.set("content", content.getPublicFeedback().deepCopy());
            item.put("voiceAnalysisEnabled", voiceAnalysisEnabled);
            item.put("completed", true);
            questionFeedback.add(item);

            canonical.append('|').append(answer.getTurn().getQuestionOrder())
                    .append(':').append(answer.getAnswerId())
                    .append(':').append(cv.getSchemaVersion())
                    .append(':').append(cv.getGazeScore())
                    .append(':').append(cv.getPostureScore())
                    .append(':').append(cv.getPublicFeedback())
                    .append(':').append(voiceAnalysisEnabled
                            ? voice.getSchemaVersion()
                            : "VOICE_SKIPPED_NO_CONSENT")
                    .append(':').append(voiceAnalysisEnabled
                            ? voice.getSpeechScore()
                            : "null")
                    .append(':').append(voiceAnalysisEnabled
                            ? voice.getPublicFeedback()
                            : "[]")
                    .append(':').append(content.getSchemaVersion())
                    .append(':').append(content.getContentScore())
                    .append(':').append(content.getPublicFeedback());
        }

        EnumMap<ReportAxis, BigDecimal> averages = new EnumMap<>(ReportAxis.class);
        for (ReportAxis axis : scores.keySet()) {
            averages.put(axis, average(scores.get(axis)));
        }
        BigDecimal overall = average(List.copyOf(averages.values()));
        return new AggregatedReport(
                SCHEMA_VERSION,
                sha256(canonical.toString()),
                overall,
                averages.get(ReportAxis.GAZE),
                averages.get(ReportAxis.POSTURE),
                averages.get(ReportAxis.SPEECH),
                averages.get(ReportAxis.CONTENT),
                insights(averages, results, true),
                insights(averages, results, false),
                questionFeedback
        );
    }

    private InterviewAnalysisResult unique(
            List<InterviewAnalysisResult> results,
            InterviewJobType type
    ) {
        List<InterviewAnalysisResult> matches = results.stream()
                .filter(result -> result.getAnalysisType() == type)
                .toList();
        if (matches.size() != 1) {
            throw new IllegalArgumentException("답변 분석 결과가 완전하지 않습니다.");
        }
        return matches.getFirst();
    }

    private void add(
            Map<ReportAxis, List<BigDecimal>> scores,
            ReportAxis axis,
            BigDecimal score
    ) {
        if (score == null) {
            throw new IllegalArgumentException("필수 점수가 누락되었습니다.");
        }
        scores.get(axis).add(score);
    }

    private BigDecimal average(List<BigDecimal> values) {
        if (values.isEmpty() || values.stream().anyMatch(value -> value == null)) {
            throw new IllegalArgumentException("평균을 계산할 점수가 없습니다.");
        }
        BigDecimal sum = values.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
        return sum.divide(
                BigDecimal.valueOf(values.size()),
                1,
                RoundingMode.HALF_UP
        );
    }

    private ArrayNode insights(
            Map<ReportAxis, BigDecimal> scores,
            List<InterviewAnalysisResult> results,
            boolean strengths
    ) {
        Comparator<ReportAxis> comparator = Comparator
                .comparing((ReportAxis axis) -> scores.get(axis))
                .thenComparingInt(ReportAxis::ordinal);
        if (strengths) {
            comparator = Comparator
                    .comparing((ReportAxis axis) -> scores.get(axis))
                    .reversed()
                    .thenComparingInt(ReportAxis::ordinal);
        }
        ArrayNode output = objectMapper.createArrayNode();
        scores.keySet().stream()
                .sorted(comparator)
                .limit(2)
                .forEach(axis -> {
                    ObjectNode item = output.addObject();
                    item.put("axis", axis.name());
                    item.put("score", scores.get(axis));
                    ArrayNode feedback = item.putArray("feedback");
                    publicFeedback(axis, results).forEach(feedback::add);
                });
        return output;
    }

    private List<String> publicFeedback(
            ReportAxis axis,
            List<InterviewAnalysisResult> results
    ) {
        InterviewJobType type = switch (axis) {
            case GAZE, POSTURE -> InterviewJobType.CV;
            case SPEECH -> InterviewJobType.VOICE;
            case CONTENT -> InterviewJobType.CONTENT;
        };
        return results.stream()
                .filter(result -> result.getAnalysisType() == type)
                .flatMap(result -> {
                    List<String> values = new ArrayList<>();
                    result.getPublicFeedback().forEach(node -> values.add(node.asText()));
                    return values.stream();
                })
                .distinct()
                .sorted()
                .limit(3)
                .toList();
    }

    private String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exception);
        }
    }
}
