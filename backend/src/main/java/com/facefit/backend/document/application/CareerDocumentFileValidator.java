package com.facefit.backend.document.application;

import com.facefit.backend.common.exception.InvalidDocumentFileException;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.encryption.InvalidPasswordException;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.w3c.dom.Document;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Component
public class CareerDocumentFileValidator {

    public static final long MAX_FILE_SIZE_BYTES = 10L * 1024L * 1024L;
    private static final int MAX_FILE_NAME_LENGTH = 255;
    private static final int MAX_ZIP_ENTRIES = 1_000;
    private static final long MAX_ZIP_UNCOMPRESSED_BYTES = 50L * 1024L * 1024L;
    private static final long MAX_ZIP_RATIO = 100L;
    private static final String PDF_MIME = "application/pdf";
    private static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private static final Set<String> MACRO_ENTRY_NAMES = Set.of(
            "word/vbaproject.bin",
            "vbaproject.bin"
    );

    public ValidatedDocumentFile validate(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new InvalidDocumentFileException("업로드 파일이 비어 있습니다.");
        }
        if (file.getSize() > MAX_FILE_SIZE_BYTES) {
            throw new InvalidDocumentFileException("파일은 10MB 이하여야 합니다.");
        }
        String safeName = safeFileName(file.getOriginalFilename());
        String extension = extensionOf(safeName);
        String expectedMime = switch (extension) {
            case "pdf" -> PDF_MIME;
            case "docx" -> DOCX_MIME;
            default -> throw new InvalidDocumentFileException(
                    "PDF 또는 DOCX 파일만 업로드할 수 있습니다."
            );
        };
        if (!expectedMime.equals(file.getContentType())) {
            throw new InvalidDocumentFileException("파일 MIME 타입이 확장자와 일치하지 않습니다.");
        }
        byte[] content;
        try {
            content = file.getBytes();
        } catch (IOException exception) {
            throw new InvalidDocumentFileException("파일을 읽을 수 없습니다.", exception);
        }
        if (content.length == 0 || content.length > MAX_FILE_SIZE_BYTES) {
            throw new InvalidDocumentFileException("파일 크기가 올바르지 않습니다.");
        }
        if ("pdf".equals(extension)) {
            validatePdf(content);
        } else {
            validateDocx(content);
        }
        return new ValidatedDocumentFile(safeName, extension, expectedMime, content);
    }

    private void validatePdf(byte[] content) {
        try (PDDocument document = Loader.loadPDF(content)) {
            if (document.isEncrypted()) {
                throw new InvalidDocumentFileException("암호화된 PDF는 업로드할 수 없습니다.");
            }
            if (document.getNumberOfPages() < 1) {
                throw new InvalidDocumentFileException("페이지가 없는 PDF는 업로드할 수 없습니다.");
            }
        } catch (InvalidPasswordException exception) {
            throw new InvalidDocumentFileException("비밀번호가 설정된 PDF는 업로드할 수 없습니다.");
        } catch (IOException | RuntimeException exception) {
            if (exception instanceof InvalidDocumentFileException invalid) {
                throw invalid;
            }
            throw new InvalidDocumentFileException("손상되었거나 올바르지 않은 PDF입니다.");
        }
    }

    private void validateDocx(byte[] content) {
        if (content.length < 4
                || content[0] != 'P'
                || content[1] != 'K'
                || content[2] != 3
                || content[3] != 4) {
            throw new InvalidDocumentFileException("올바른 DOCX 컨테이너가 아닙니다.");
        }

        Map<String, byte[]> requiredParts = new HashMap<>();
        long totalUncompressed = 0;
        int entryCount = 0;
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(content))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entryCount++;
                if (entryCount > MAX_ZIP_ENTRIES) {
                    throw new InvalidDocumentFileException("DOCX 내부 항목 수가 허용 범위를 초과합니다.");
                }
                String normalizedName = entry.getName().replace('\\', '/').toLowerCase(Locale.ROOT);
                if (normalizedName.startsWith("/")
                        || normalizedName.contains("../")
                        || normalizedName.equals("encryptioninfo")
                        || normalizedName.equals("encryptedpackage")
                        || MACRO_ENTRY_NAMES.contains(normalizedName)
                        || normalizedName.endsWith("/vbaproject.bin")) {
                    throw new InvalidDocumentFileException(
                            "암호화되었거나 매크로가 포함된 DOCX는 업로드할 수 없습니다."
                    );
                }

                ByteArrayOutputStream entryBytes = new ByteArrayOutputStream();
                byte[] buffer = new byte[8_192];
                int read;
                while ((read = zip.read(buffer)) != -1) {
                    totalUncompressed += read;
                    long ratioLimit = Math.max(content.length * MAX_ZIP_RATIO, content.length);
                    if (totalUncompressed > MAX_ZIP_UNCOMPRESSED_BYTES
                            || totalUncompressed > ratioLimit) {
                        throw new InvalidDocumentFileException(
                                "DOCX 압축 해제 크기가 안전 범위를 초과합니다."
                        );
                    }
                    if (isRequiredPart(normalizedName)) {
                        entryBytes.write(buffer, 0, read);
                    }
                }
                if (isRequiredPart(normalizedName)) {
                    requiredParts.put(normalizedName, entryBytes.toByteArray());
                }
            }
        } catch (InvalidDocumentFileException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new InvalidDocumentFileException("손상된 DOCX 압축 구조입니다.");
        }

        for (String required : Set.of(
                "[content_types].xml",
                "_rels/.rels",
                "word/document.xml"
        )) {
            if (!requiredParts.containsKey(required)) {
                throw new InvalidDocumentFileException("필수 OOXML 구조가 없는 DOCX입니다.");
            }
        }
        Document contentTypes = parseXml(requiredParts.get("[content_types].xml"));
        Document document = parseXml(requiredParts.get("word/document.xml"));
        parseXml(requiredParts.get("_rels/.rels"));

        String contentTypesText = contentTypes.getDocumentElement().getTextContent();
        String serializedContentTypes = new String(
                requiredParts.get("[content_types].xml"),
                java.nio.charset.StandardCharsets.UTF_8
        ).toLowerCase(Locale.ROOT);
        if (!serializedContentTypes.contains(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        ) || serializedContentTypes.contains("macroenabled")
                || serializedContentTypes.contains("vbaproject")) {
            throw new InvalidDocumentFileException("DOCX 문서 형식 또는 매크로 구성이 올바르지 않습니다.");
        }
        if (!"document".equalsIgnoreCase(document.getDocumentElement().getLocalName())
                && !document.getDocumentElement().getNodeName().endsWith(":document")) {
            throw new InvalidDocumentFileException("DOCX 본문 구조가 올바르지 않습니다.");
        }
        if (contentTypesText == null) {
            throw new InvalidDocumentFileException("DOCX Content Types 구조가 올바르지 않습니다.");
        }
    }

    private Document parseXml(byte[] content) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            return factory.newDocumentBuilder().parse(new ByteArrayInputStream(content));
        } catch (Exception exception) {
            throw new InvalidDocumentFileException("손상된 DOCX XML 구조입니다.");
        }
    }

    private boolean isRequiredPart(String name) {
        return "[content_types].xml".equals(name)
                || "_rels/.rels".equals(name)
                || "word/document.xml".equals(name);
    }

    private String safeFileName(String originalFileName) {
        if (originalFileName == null || originalFileName.isBlank()) {
            throw new InvalidDocumentFileException("원본 파일명이 필요합니다.");
        }
        if (originalFileName.indexOf('\0') >= 0) {
            throw new InvalidDocumentFileException("파일명에 허용되지 않는 문자가 있습니다.");
        }
        try {
            String safeName = Path.of(originalFileName).getFileName().toString();
            safeName = Path.of(safeName.replace('\\', '/')).getFileName().toString();
            if (safeName.isBlank() || safeName.length() > MAX_FILE_NAME_LENGTH) {
                throw new InvalidDocumentFileException("파일명 길이가 올바르지 않습니다.");
            }
            return safeName;
        } catch (InvalidPathException exception) {
            throw new InvalidDocumentFileException("파일명이 올바르지 않습니다.");
        }
    }

    private String extensionOf(String fileName) {
        int dot = fileName.lastIndexOf('.');
        if (dot < 1 || dot == fileName.length() - 1) {
            throw new InvalidDocumentFileException("파일 확장자가 필요합니다.");
        }
        String extension = fileName.substring(dot + 1);
        return extension.toLowerCase(Locale.ROOT);
    }
}
