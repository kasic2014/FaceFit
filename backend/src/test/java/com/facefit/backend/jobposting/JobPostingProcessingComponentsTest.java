package com.facefit.backend.jobposting;

import com.facefit.backend.jobposting.application.DeterministicJobPostingStructurer;
import com.facefit.backend.jobposting.application.JobPostingTextNormalizer;
import com.facefit.backend.jobposting.application.JobProcessingException;
import com.facefit.backend.jobposting.domain.StructuredJobPosting;
import com.facefit.backend.jobposting.extraction.DocxJobPostingTextExtractor;
import com.facefit.backend.jobposting.extraction.ImageJobPostingTextExtractor;
import com.facefit.backend.jobposting.extraction.Hwp5JobPostingTextExtractor;
import com.facefit.backend.jobposting.extraction.PdfJobPostingTextExtractor;
import com.facefit.backend.jobposting.extraction.SafeImageDecoder;
import com.facefit.backend.jobposting.ocr.ExifOrientationNormalizer;
import com.facefit.backend.jobposting.ocr.OcrCommandRunner;
import com.facefit.backend.jobposting.ocr.OcrEngine;
import com.facefit.backend.jobposting.ocr.TesseractOcrEngine;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.Document;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class JobPostingProcessingComponentsTest {

    @Test
    void normalizerUsesNfkcRemovesControlsAndEnforcesCodePointLimit() {
        JobPostingTextNormalizer normalizer = new JobPostingTextNormalizer(12);

        String normalized = normalizer.normalize(" ＦａｃｅＦｉｔ \r\n\r\n\r\n 직무\u0000  :  개발😀자 ");

        assertThat(normalized).isEqualTo("FaceFit\n\n직무");
        assertThat(normalized.codePointCount(0, normalized.length())).isLessThanOrEqualTo(12);
    }

    @Test
    void deterministicStructurerMapsAliasesDeduplicatesAndDoesNotGuess() {
        DeterministicJobPostingStructurer structurer = new DeterministicJobPostingStructurer();
        String text = """
                임의 서문은 어떤 필드에도 추정해서 넣지 않는다.
                회사명: FaceFit
                포지션 - 백엔드 개발자
                주요 업무
                - API 설계
                - API 설계
                자격 요건: Java 경험
                우대 사항
                PostgreSQL 경험
                기술 스택: Java, Spring
                핵심 역량: 문제 해결
                회사 소개
                AI 면접 서비스
                """;

        StructuredJobPosting result = structurer.structure(text);

        assertThat(result.companyName()).isEqualTo("FaceFit");
        assertThat(result.targetRole()).isEqualTo("백엔드 개발자");
        assertThat(result.mainResponsibilities()).isEqualTo("API 설계");
        assertThat(result.qualifications()).isEqualTo("Java 경험");
        assertThat(result.preferredQualifications()).isEqualTo("PostgreSQL 경험");
        assertThat(result.technologiesTools()).isEqualTo("Java, Spring");
        assertThat(result.coreCompetencies()).isEqualTo("문제 해결");
        assertThat(result.companyBusinessIntro()).isEqualTo("AI 면접 서비스");
        assertThat(result.hasRequiredFields()).isTrue();
    }

    @Test
    void pdfUsesNativeTextAndOcrOnlyForLowTextPages() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        when(ocr.recognize(any())).thenReturn("OCR blank page");
        PdfJobPostingTextExtractor extractor = new PdfJobPostingTextExtractor(ocr, 20, 72);

        String result = extractor.extract(mixedPdf());

        assertThat(result).contains("This page already contains enough searchable text");
        assertThat(result).contains("OCR blank page");
        verify(ocr, times(1)).recognize(any());
    }

    @Test
    void textPdfDoesNotCallOcr() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        PdfJobPostingTextExtractor extractor = new PdfJobPostingTextExtractor(ocr, 20, 72);

        assertThat(extractor.extract(textPdf()))
                .contains("enough searchable text");
        verify(ocr, times(0)).recognize(any());
    }

    @Test
    void scannedPdfCallsOcr() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        when(ocr.recognize(any())).thenReturn("스캔 공고 OCR");
        PdfJobPostingTextExtractor extractor = new PdfJobPostingTextExtractor(ocr, 20, 72);

        assertThat(extractor.extract(blankPdf())).isEqualTo("스캔 공고 OCR");
        verify(ocr).recognize(any());
    }

    @Test
    void imageExtractionDecodesAndDelegatesToOcr() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        when(ocr.recognize(any())).thenReturn("회사명 FaceFit");
        SafeImageDecoder decoder = new SafeImageDecoder(
                100,
                new ExifOrientationNormalizer()
        );
        ImageJobPostingTextExtractor extractor = new ImageJobPostingTextExtractor(decoder, ocr);

        assertThat(extractor.extract(png())).isEqualTo("회사명 FaceFit");
        verify(ocr).recognize(any());
    }

    @Test
    void docxExtractsParagraphsAndTablesWithoutOcrWhenThereAreNoImages() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        SafeImageDecoder decoder = new SafeImageDecoder(
                1_000,
                new ExifOrientationNormalizer()
        );
        DocxJobPostingTextExtractor extractor = new DocxJobPostingTextExtractor(decoder, ocr);

        String result = extractor.extract(docxWithTable());

        assertThat(result).contains("회사명: FaceFit");
        assertThat(result).contains("주요 업무", "API 설계");
        verify(ocr, times(0)).recognize(any());
    }

    @Test
    void docxCombinesEmbeddedImageOcrWithDocumentText() throws Exception {
        OcrEngine ocr = mock(OcrEngine.class);
        when(ocr.recognize(any())).thenReturn("이미지 안의 자격요건");
        SafeImageDecoder decoder = new SafeImageDecoder(
                1_000,
                new ExifOrientationNormalizer()
        );
        DocxJobPostingTextExtractor extractor = new DocxJobPostingTextExtractor(decoder, ocr);

        String result = extractor.extract(docxWithImage());

        assertThat(result).contains("회사명: FaceFit", "이미지 안의 자격요건");
        verify(ocr).recognize(any());
    }

    @Test
    void tesseractAdapterPassesKorEngTimeoutAndAlwaysDeletesTemporaryFile() {
        AtomicReference<Path> capturedImage = new AtomicReference<>();
        OcrCommandRunner runner = (input, languages, timeout) -> {
            assertThat(Files.exists(input)).isTrue();
            assertThat(languages).isEqualTo("kor+eng");
            assertThat(timeout).isEqualTo(Duration.ofSeconds(7));
            capturedImage.set(input);
            return "recognized";
        };
        TesseractOcrEngine engine = new TesseractOcrEngine(runner, true, "kor+eng", 7);

        assertThat(engine.recognize(new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB)))
                .isEqualTo("recognized");
        assertThat(capturedImage.get()).isNotNull();
        assertThat(Files.exists(capturedImage.get())).isFalse();
        assertThat(Files.exists(capturedImage.get().getParent())).isFalse();
    }

    @Test
    void disabledOcrReturnsStableInternalErrorCode() {
        TesseractOcrEngine engine = new TesseractOcrEngine(
                mock(OcrCommandRunner.class),
                false,
                "kor+eng",
                7
        );

        assertThatThrownBy(() -> engine.recognize(
                new BufferedImage(1, 1, BufferedImage.TYPE_INT_RGB)
        )).isInstanceOfSatisfying(JobProcessingException.class,
                exception -> {
                    assertThat(exception.getErrorCode()).isEqualTo("OCR_DISABLED");
                    assertThat(exception.isRetryable()).isFalse();
                });
    }

    @Test
    void forkedHwpParserReturnsStableFailureForCorruptInput() {
        Hwp5JobPostingTextExtractor extractor =
                new Hwp5JobPostingTextExtractor(5, 50_000, 64);

        assertThatThrownBy(() -> extractor.extract("not-hwp".getBytes()))
                .isInstanceOfSatisfying(JobProcessingException.class,
                        exception -> assertThat(exception.getErrorCode())
                                .isEqualTo("HWP_EXTRACTION_FAILED"));
    }

    private byte[] mixedPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            PDPage textPage = new PDPage();
            document.addPage(textPage);
            try (PDPageContentStream stream = new PDPageContentStream(document, textPage)) {
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(50, 700);
                stream.showText("This page already contains enough searchable text for extraction.");
                stream.endText();
            }
            document.addPage(new PDPage());
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] textPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream stream = new PDPageContentStream(document, page)) {
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(50, 700);
                stream.showText("This page contains enough searchable text for extraction.");
                stream.endText();
            }
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] blankPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] docxWithTable() throws Exception {
        try (XWPFDocument document = new XWPFDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("회사명: FaceFit");
            XWPFTable table = document.createTable(1, 2);
            table.getRow(0).getCell(0).setText("주요 업무");
            table.getRow(0).getCell(1).setText("API 설계");
            document.write(output);
            return output.toByteArray();
        }
    }

    private byte[] docxWithImage() throws Exception {
        byte[] picture = png();
        try (XWPFDocument document = new XWPFDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("회사명: FaceFit");
            document.createParagraph().createRun().addPicture(
                    new ByteArrayInputStream(picture),
                    Document.PICTURE_TYPE_PNG,
                    "posting.png",
                    20,
                    20
            );
            document.write(output);
            return output.toByteArray();
        }
    }

    private byte[] png() throws Exception {
        BufferedImage image = new BufferedImage(3, 2, BufferedImage.TYPE_INT_RGB);
        try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            ImageIO.write(image, "png", output);
            return output.toByteArray();
        }
    }
}
