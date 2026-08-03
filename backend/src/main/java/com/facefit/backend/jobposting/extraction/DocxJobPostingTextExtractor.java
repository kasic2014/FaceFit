package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.application.JobProcessingException;
import com.facefit.backend.jobposting.ocr.OcrEngine;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFFooter;
import org.apache.poi.xwpf.usermodel.XWPFHeader;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFPictureData;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;
import org.apache.xmlbeans.XmlObject;
import org.springframework.stereotype.Component;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Component
public class DocxJobPostingTextExtractor {

    private static final String WORD_NAMESPACE =
            "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

    private final SafeImageDecoder imageDecoder;
    private final OcrEngine ocrEngine;

    public DocxJobPostingTextExtractor(SafeImageDecoder imageDecoder, OcrEngine ocrEngine) {
        this.imageDecoder = imageDecoder;
        this.ocrEngine = ocrEngine;
    }

    public String extract(byte[] content) {
        try (XWPFDocument document = new XWPFDocument(new ByteArrayInputStream(content))) {
            List<String> sections = new ArrayList<>();
            appendParagraphs(sections, document.getParagraphs());
            appendTables(sections, document.getTables());
            for (XWPFHeader header : document.getHeaderList()) {
                appendParagraphs(sections, header.getParagraphs());
                appendTables(sections, header.getTables());
            }
            for (XWPFFooter footer : document.getFooterList()) {
                appendParagraphs(sections, footer.getParagraphs());
                appendTables(sections, footer.getTables());
            }
            for (XWPFPictureData picture : document.getAllPictures()) {
                try {
                    String recognized = ocrEngine.recognize(
                            imageDecoder.decode(picture.getData(), false)
                    );
                    if (recognized != null && !recognized.isBlank()) {
                        sections.add(recognized);
                    }
                } catch (JobProcessingException imageFailure) {
                    if (!"IMAGE_DECODE_FAILED".equals(imageFailure.getErrorCode())) {
                        throw imageFailure;
                    }
                }
            }
            return String.join("\n", sections);
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (IOException | RuntimeException exception) {
            throw new JobProcessingException("DOCX_EXTRACTION_FAILED", false, exception);
        }
    }

    private void appendParagraphs(List<String> output, List<XWPFParagraph> paragraphs) {
        for (XWPFParagraph paragraph : paragraphs) {
            String text = paragraph.getText();
            if (text == null || text.isBlank()) {
                text = textNodes(paragraph);
            }
            if (text != null && !text.isBlank()) {
                output.add(text);
            }
        }
    }

    private void appendTables(List<String> output, List<XWPFTable> tables) {
        for (XWPFTable table : tables) {
            for (XWPFTableRow row : table.getRows()) {
                List<String> cells = new ArrayList<>();
                for (XWPFTableCell cell : row.getTableCells()) {
                    String value = cell.getText();
                    if (value != null && !value.isBlank()) {
                        cells.add(value);
                    }
                    appendTables(output, cell.getTables());
                }
                if (!cells.isEmpty()) {
                    output.add(String.join("\t", cells));
                }
            }
        }
    }

    private String textNodes(XWPFParagraph paragraph) {
        XmlObject[] nodes = paragraph.getCTP().selectPath(
                "declare namespace w='" + WORD_NAMESPACE + "' .//w:t"
        );
        StringBuilder text = new StringBuilder();
        for (XmlObject node : nodes) {
            String value = node.newCursor().getTextValue();
            if (value != null) {
                text.append(value);
            }
        }
        return text.toString();
    }
}
