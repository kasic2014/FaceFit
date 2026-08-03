package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.application.JobProcessingException;
import com.facefit.backend.jobposting.ocr.OcrEngine;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Component
public class PdfJobPostingTextExtractor {

    private final OcrEngine ocrEngine;
    private final int minimumTextCharacters;
    private final float ocrDpi;

    public PdfJobPostingTextExtractor(
            OcrEngine ocrEngine,
            @Value("${facefit.job-postings.pdf-min-text-characters:20}") int minimumTextCharacters,
            @Value("${facefit.job-postings.pdf-ocr-dpi:300}") float ocrDpi
    ) {
        this.ocrEngine = ocrEngine;
        this.minimumTextCharacters = minimumTextCharacters;
        this.ocrDpi = ocrDpi;
    }

    public String extract(byte[] content) {
        try (PDDocument document = Loader.loadPDF(content)) {
            PDFRenderer renderer = new PDFRenderer(document);
            List<String> pages = new ArrayList<>(document.getNumberOfPages());
            for (int pageIndex = 0; pageIndex < document.getNumberOfPages(); pageIndex++) {
                String pageText = extractPageText(document, pageIndex + 1);
                if (visibleCharacterCount(pageText) < minimumTextCharacters) {
                    pageText = ocrEngine.recognize(
                            renderer.renderImageWithDPI(pageIndex, ocrDpi, ImageType.RGB)
                    );
                }
                pages.add(pageText == null ? "" : pageText);
            }
            return String.join("\n\n", pages);
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (IOException | RuntimeException exception) {
            throw new JobProcessingException("PDF_EXTRACTION_FAILED", false, exception);
        }
    }

    private String extractPageText(PDDocument document, int pageNumber) throws IOException {
        PDFTextStripper stripper = new PDFTextStripper();
        stripper.setStartPage(pageNumber);
        stripper.setEndPage(pageNumber);
        stripper.setSortByPosition(true);
        return stripper.getText(document);
    }

    private long visibleCharacterCount(String value) {
        if (value == null) {
            return 0;
        }
        return value.codePoints().filter(codePoint -> !Character.isWhitespace(codePoint)).count();
    }
}
