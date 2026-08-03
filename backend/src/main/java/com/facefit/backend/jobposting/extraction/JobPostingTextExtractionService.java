package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.application.JobPostingFileFormat;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class JobPostingTextExtractionService {

    private final PdfJobPostingTextExtractor pdfExtractor;
    private final DocxJobPostingTextExtractor docxExtractor;
    private final ImageJobPostingTextExtractor imageExtractor;
    private final Hwp5JobPostingTextExtractor hwpExtractor;

    public String extract(JobPostingFileFormat format, byte[] content) {
        return switch (format) {
            case PDF -> pdfExtractor.extract(content);
            case DOCX -> docxExtractor.extract(content);
            case JPEG, PNG -> imageExtractor.extract(content);
            case HWP5 -> hwpExtractor.extract(content);
        };
    }
}
