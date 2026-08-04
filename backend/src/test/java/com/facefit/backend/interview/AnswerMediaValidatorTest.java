package com.facefit.backend.interview;

import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.interview.application.AnswerMediaValidator;
import com.facefit.backend.interview.application.ValidatedAnswerMedia;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnswerMediaValidatorTest {

    private final AnswerMediaValidator validator = new AnswerMediaValidator(
            Path.of(System.getProperty("java.io.tmpdir"), "facefit-answer-tests")
    );

    @Test
    void acceptsStructuredMp4WithVideoAudioAndBoundedDuration() {
        ValidatedAnswerMedia result = validator.validate(
                file("video/mp4", TestMediaFiles.mp4(true, true, 60)),
                60
        );

        assertThat(result.mimeType()).isEqualTo("video/mp4");
        assertThat(result.extension()).isEqualTo("mp4");
        assertThat(result.durationMillis()).isEqualTo(60_000);
        assertThat(result.sha256()).hasSize(64);
        result.close();
    }

    @Test
    void acceptsStructuredWebmWithVideoAudioAndBoundedDuration() {
        ValidatedAnswerMedia result = validator.validate(
                file("video/webm", TestMediaFiles.webm(true, true, 45)),
                45
        );

        assertThat(result.mimeType()).isEqualTo("video/webm");
        assertThat(result.extension()).isEqualTo("webm");
        assertThat(result.durationMillis()).isEqualTo(45_000);
        result.close();
    }

    @Test
    void rejectsMimeMismatchMissingStreamsAndExcessiveDuration() {
        assertInvalid(file(
                "video/webm",
                TestMediaFiles.mp4(true, true, 30)
        ), 30);
        assertInvalid(file(
                "video/mp4",
                TestMediaFiles.mp4(true, false, 30)
        ), 30);
        assertInvalid(file(
                "video/webm",
                TestMediaFiles.webm(true, true, 301)
        ), 300);
    }

    @Test
    void rejectsSignatureSpoofAndInvalidDeclaredDuration() {
        assertInvalid(file(
                "video/mp4",
                "not-an-mp4".getBytes()
        ), 10);
        assertInvalid(file(
                "video/mp4",
                TestMediaFiles.mp4(true, true, 10)
        ), 0);
    }

    private MockMultipartFile file(String mime, byte[] content) {
        return new MockMultipartFile("file", "ignored.bin", mime, content);
    }

    private void assertInvalid(MockMultipartFile file, int duration) {
        assertThatThrownBy(() -> validator.validate(file, duration))
                .isInstanceOf(InterviewProgressException.class)
                .extracting(exception ->
                        ((InterviewProgressException) exception).getErrorCode()
                )
                .isEqualTo("INVALID_ANSWER_MEDIA");
    }
}
