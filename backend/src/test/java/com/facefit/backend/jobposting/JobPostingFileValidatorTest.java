package com.facefit.backend.jobposting;

import com.facefit.backend.common.exception.JobPostingFileException;
import com.facefit.backend.jobposting.application.JobPostingFileFormat;
import com.facefit.backend.jobposting.application.JobPostingFileValidator;
import com.facefit.backend.jobposting.application.ValidatedJobPostingFile;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.encryption.AccessPermission;
import org.apache.pdfbox.pdmodel.encryption.StandardProtectionPolicy;
import org.apache.poi.poifs.filesystem.DirectoryEntry;
import org.apache.poi.poifs.filesystem.POIFSFileSystem;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import javax.imageio.ImageIO;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JobPostingFileValidatorTest {

    private static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private final JobPostingFileValidator validator = new JobPostingFileValidator(50, 40_000_000);

    @Test
    void acceptsAndNormalizesEveryAllowedFormat() throws Exception {
        assertValidated(file("posting.pdf", "application/pdf", pdf(false)),
                JobPostingFileFormat.PDF, "application/pdf");
        assertValidated(file("posting.docx", DOCX_MIME, docx()),
                JobPostingFileFormat.DOCX, DOCX_MIME);
        assertValidated(file("posting.jpg", "image/jpeg", image("jpg")),
                JobPostingFileFormat.JPEG, "image/jpeg");
        assertValidated(file("posting.jpeg", "image/jpeg", image("jpeg")),
                JobPostingFileFormat.JPEG, "image/jpeg");
        assertValidated(file("posting.png", "image/png", image("png")),
                JobPostingFileFormat.PNG, "image/png");

        ValidatedJobPostingFile hwp = validator.validate(file(
                "posting.hwp",
                "application/haansofthwp",
                hwp(5, 0)
        ));
        assertThat(hwp.format()).isEqualTo(JobPostingFileFormat.HWP5);
        assertThat(hwp.mimeType()).isEqualTo("application/x-hwp-v5");
    }

    @Test
    void rejectsExtensionMimeAndActualFormatDisguises() throws Exception {
        assertUnsupported(file("posting.exe", "application/octet-stream", pdf(false)));
        assertUnsupported(file("posting.pdf", "text/plain", pdf(false)));
        assertUnsupported(file("posting.pdf", "application/pdf", image("png")));
        assertUnsupported(file("posting.hwp", "application/x-hwp", docx()));
        assertUnsupported(file("posting.hwpx", "application/zip", docx()));
    }

    @Test
    void rejectsEmptyAndOversizedFiles() {
        assertThatThrownBy(() -> validator.validate(file(
                "empty.pdf",
                "application/pdf",
                new byte[0]
        ))).isInstanceOfSatisfying(JobPostingFileException.class,
                exception -> assertThat(exception.getErrorCode()).isEqualTo("INVALID_FILE"));

        assertThatThrownBy(() -> validator.validate(file(
                "large.pdf",
                "application/pdf",
                new byte[(int) JobPostingFileValidator.MAX_FILE_SIZE_BYTES + 1]
        ))).isInstanceOfSatisfying(JobPostingFileException.class,
                exception -> assertThat(exception.getErrorCode()).isEqualTo("FILE_TOO_LARGE"));
    }

    @Test
    void rejectsEncryptedAndExcessivePagePdf() throws Exception {
        assertUnsupported(file("secret.pdf", "application/pdf", pdf(true)));

        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            document.addPage(new PDPage());
            document.save(output);
            JobPostingFileValidator onePageValidator =
                    new JobPostingFileValidator(1, 40_000_000);
            assertThatThrownBy(() -> onePageValidator.validate(file(
                    "long.pdf",
                    "application/pdf",
                    output.toByteArray()
            ))).isInstanceOfSatisfying(JobPostingFileException.class,
                    exception -> assertThat(exception.getErrorCode())
                            .isEqualTo("FILE_TYPE_NOT_SUPPORTED"));
        }
    }

    @Test
    void rejectsHwpOlderVersionEncryptionDistributionCorruptionAndMissingStreams() throws Exception {
        assertUnsupported(file("old.hwp", "application/x-hwp", hwp(3, 0)));
        assertUnsupported(file("encrypted.hwp", "application/x-hwp", hwp(5, 1 << 1)));
        assertUnsupported(file("distribution.hwp", "application/x-hwp", hwp(5, 1 << 2)));
        assertUnsupported(file(
                "corrupt.hwp",
                "application/x-hwp",
                "HWP Document File".getBytes(StandardCharsets.US_ASCII)
        ));
        assertUnsupported(file("missing.hwp", "application/x-hwp", hwpWithoutBodyText()));
    }

    @Test
    void stripsPathComponentsFromOriginalFileName() throws Exception {
        ValidatedJobPostingFile validated = validator.validate(file(
                "..\\..\\posting.pdf",
                "application/pdf",
                pdf(false)
        ));
        assertThat(validated.originalFileName()).isEqualTo("posting.pdf");
    }

    private void assertValidated(
            MockMultipartFile file,
            JobPostingFileFormat expectedFormat,
            String expectedMime
    ) {
        ValidatedJobPostingFile validated = validator.validate(file);
        assertThat(validated.format()).isEqualTo(expectedFormat);
        assertThat(validated.mimeType()).isEqualTo(expectedMime);
        assertThat(validated.size()).isPositive();
    }

    private void assertUnsupported(MockMultipartFile file) {
        assertThatThrownBy(() -> validator.validate(file))
                .isInstanceOfSatisfying(JobPostingFileException.class,
                        exception -> assertThat(exception.getErrorCode())
                                .isEqualTo("FILE_TYPE_NOT_SUPPORTED"));
    }

    private MockMultipartFile file(String name, String mime, byte[] content) {
        return new MockMultipartFile("file", name, mime, content);
    }

    private byte[] pdf(boolean encrypted) throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            if (encrypted) {
                StandardProtectionPolicy policy = new StandardProtectionPolicy(
                        "owner-password",
                        "user-password",
                        new AccessPermission()
                );
                policy.setEncryptionKeyLength(128);
                document.protect(policy);
            }
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] docx() throws Exception {
        try (XWPFDocument document = new XWPFDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("FaceFit 채용 공고");
            document.write(output);
            return output.toByteArray();
        }
    }

    private byte[] image(String format) throws Exception {
        BufferedImage image = new BufferedImage(4, 3, BufferedImage.TYPE_INT_RGB);
        image.setRGB(0, 0, Color.BLUE.getRGB());
        try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            assertThat(ImageIO.write(image, format, output)).isTrue();
            return output.toByteArray();
        }
    }

    private byte[] hwp(int majorVersion, int properties) throws Exception {
        try (POIFSFileSystem fileSystem = new POIFSFileSystem();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            DirectoryEntry root = fileSystem.getRoot();
            root.createDocument("FileHeader", new ByteArrayInputStream(hwpHeader(
                    majorVersion,
                    properties
            )));
            root.createDocument("DocInfo", new ByteArrayInputStream(new byte[]{0, 0, 0, 0}));
            DirectoryEntry bodyText = root.createDirectory("BodyText");
            bodyText.createDocument("Section0", new ByteArrayInputStream(new byte[]{0, 0, 0, 0}));
            fileSystem.writeFilesystem(output);
            return output.toByteArray();
        }
    }

    private byte[] hwpWithoutBodyText() throws Exception {
        try (POIFSFileSystem fileSystem = new POIFSFileSystem();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            DirectoryEntry root = fileSystem.getRoot();
            root.createDocument("FileHeader", new ByteArrayInputStream(hwpHeader(5, 0)));
            root.createDocument("DocInfo", new ByteArrayInputStream(new byte[]{0, 0, 0, 0}));
            fileSystem.writeFilesystem(output);
            return output.toByteArray();
        }
    }

    private byte[] hwpHeader(int majorVersion, int properties) {
        byte[] header = new byte[256];
        byte[] signature = "HWP Document File".getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(signature, 0, header, 0, signature.length);
        header[32] = 0;
        header[33] = 0;
        header[34] = 0;
        header[35] = (byte) majorVersion;
        header[36] = (byte) properties;
        header[37] = (byte) (properties >>> 8);
        header[38] = (byte) (properties >>> 16);
        header[39] = (byte) (properties >>> 24);
        return header;
    }
}
