package com.facefit.backend.jobposting.application;

import com.facefit.backend.common.exception.JobPostingFileException;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.encryption.InvalidPasswordException;
import org.apache.poi.poifs.filesystem.DirectoryEntry;
import org.apache.poi.poifs.filesystem.DocumentEntry;
import org.apache.poi.poifs.filesystem.DocumentInputStream;
import org.apache.poi.poifs.filesystem.Entry;
import org.apache.poi.poifs.filesystem.POIFSFileSystem;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.w3c.dom.Document;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Component
public class JobPostingFileValidator {

    public static final long MAX_FILE_SIZE_BYTES = 10L * 1024L * 1024L;
    public static final long DEFAULT_MAX_IMAGE_PIXELS = 40_000_000L;
    public static final int DEFAULT_MAX_PDF_PAGES = 50;
    public static final String PDF_MIME = "application/pdf";
    public static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    public static final String JPEG_MIME = "image/jpeg";
    public static final String PNG_MIME = "image/png";
    public static final String HWP5_MIME = "application/x-hwp-v5";

    private static final int MAX_FILE_NAME_LENGTH = 255;
    private static final int MAX_ZIP_ENTRIES = 1_000;
    private static final long MAX_ZIP_UNCOMPRESSED_BYTES = 50L * 1024L * 1024L;
    private static final long MAX_ZIP_RATIO = 100L;
    private static final byte[] CFB_SIGNATURE = {
            (byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0,
            (byte) 0xA1, (byte) 0xB1, 0x1A, (byte) 0xE1
    };
    private static final byte[] PNG_SIGNATURE = {
            (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    };
    private static final Set<String> HWP_REQUEST_MIMES = Set.of(
            HWP5_MIME,
            "application/x-hwp",
            "application/haansofthwp",
            "application/vnd.hancom.hwp"
    );
    private static final Set<String> REQUIRED_DOCX_PARTS = Set.of(
            "[content_types].xml",
            "_rels/.rels",
            "word/document.xml"
    );

    private final int maxPdfPages;
    private final long maxImagePixels;

    public JobPostingFileValidator(
            @Value("${facefit.job-postings.max-pdf-pages:50}") int maxPdfPages,
            @Value("${facefit.job-postings.max-image-pixels:40000000}") long maxImagePixels
    ) {
        this.maxPdfPages = maxPdfPages;
        this.maxImagePixels = maxImagePixels;
    }

    public ValidatedJobPostingFile validate(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw JobPostingFileException.invalid("업로드할 파일이 필요하며 빈 파일은 허용하지 않습니다.");
        }
        if (file.getSize() > MAX_FILE_SIZE_BYTES) {
            throw JobPostingFileException.tooLarge();
        }
        String safeName = safeFileName(file.getOriginalFilename());
        String extension = extensionOf(safeName);
        FilePolicy policy = policy(extension);
        validateRequestedMime(policy, file.getContentType());

        byte[] content = read(file);
        if (content.length == 0) {
            throw JobPostingFileException.invalid("빈 파일은 허용하지 않습니다.");
        }
        if (content.length > MAX_FILE_SIZE_BYTES) {
            throw JobPostingFileException.tooLarge();
        }

        switch (policy.format()) {
            case PDF -> validatePdf(content);
            case DOCX -> validateDocx(content);
            case JPEG -> validateImage(content, "JPEG");
            case PNG -> validateImage(content, "PNG");
            case HWP5 -> validateHwp5(content);
        }
        return new ValidatedJobPostingFile(
                safeName,
                extension,
                policy.normalizedMime(),
                policy.format(),
                content
        );
    }

    private void validatePdf(byte[] content) {
        if (content.length < 5
                || content[0] != '%'
                || content[1] != 'P'
                || content[2] != 'D'
                || content[3] != 'F'
                || content[4] != '-') {
            throw JobPostingFileException.unsupported("실제 PDF 형식이 아닙니다.");
        }
        try (PDDocument document = Loader.loadPDF(content)) {
            if (document.isEncrypted()) {
                throw JobPostingFileException.unsupported("암호화된 PDF는 허용하지 않습니다.");
            }
            int pageCount = document.getNumberOfPages();
            if (pageCount < 1 || pageCount > maxPdfPages) {
                throw JobPostingFileException.unsupported(
                        "PDF 페이지 수는 1페이지 이상 %d페이지 이하여야 합니다.".formatted(maxPdfPages)
                );
            }
        } catch (InvalidPasswordException exception) {
            throw JobPostingFileException.unsupported("비밀번호로 보호된 PDF는 허용하지 않습니다.");
        } catch (IOException | RuntimeException exception) {
            if (exception instanceof JobPostingFileException fileException) {
                throw fileException;
            }
            throw JobPostingFileException.unsupported("손상되었거나 올바르지 않은 PDF입니다.");
        }
    }

    private void validateDocx(byte[] content) {
        if (!hasZipSignature(content)) {
            throw JobPostingFileException.unsupported("실제 DOCX OOXML 형식이 아닙니다.");
        }
        Map<String, byte[]> required = readSafeDocxEntries(content);
        for (String part : REQUIRED_DOCX_PARTS) {
            if (!required.containsKey(part)) {
                throw JobPostingFileException.unsupported("필수 OOXML 구조가 없는 DOCX입니다.");
            }
        }

        Document contentTypes = parseXml(required.get("[content_types].xml"));
        Document relationships = parseXml(required.get("_rels/.rels"));
        Document document = parseXml(required.get("word/document.xml"));
        String serialized = new String(
                required.get("[content_types].xml"),
                StandardCharsets.UTF_8
        ).toLowerCase(Locale.ROOT);
        if (!serialized.contains(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        ) || serialized.contains("macroenabled") || serialized.contains("vbaproject")) {
            throw JobPostingFileException.unsupported("매크로 또는 비표준 DOCX는 허용하지 않습니다.");
        }
        if (!isElement(document, "document")
                || !isElement(contentTypes, "Types")
                || !isElement(relationships, "Relationships")) {
            throw JobPostingFileException.unsupported("DOCX OOXML 구조가 올바르지 않습니다.");
        }
    }

    private Map<String, byte[]> readSafeDocxEntries(byte[] content) {
        Map<String, byte[]> required = new HashMap<>();
        long totalUncompressed = 0;
        int entryCount = 0;
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(content))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entryCount++;
                if (entryCount > MAX_ZIP_ENTRIES) {
                    throw JobPostingFileException.unsupported("DOCX ZIP 항목 수가 제한을 초과합니다.");
                }
                String name = entry.getName().replace('\\', '/').toLowerCase(Locale.ROOT);
                if (name.startsWith("/")
                        || name.contains("../")
                        || name.equals("encryptioninfo")
                        || name.equals("encryptedpackage")
                        || name.endsWith("/vbaproject.bin")
                        || name.equals("vbaproject.bin")) {
                    throw JobPostingFileException.unsupported(
                            "암호화·경로 조작·매크로가 포함된 DOCX는 허용하지 않습니다."
                    );
                }
                ByteArrayOutputStream selected = new ByteArrayOutputStream();
                byte[] buffer = new byte[8_192];
                int read;
                while ((read = zip.read(buffer)) != -1) {
                    totalUncompressed += read;
                    long ratioLimit = Math.max(content.length * MAX_ZIP_RATIO, content.length);
                    if (totalUncompressed > MAX_ZIP_UNCOMPRESSED_BYTES
                            || totalUncompressed > ratioLimit) {
                        throw JobPostingFileException.unsupported(
                                "DOCX 압축 해제 크기 또는 압축 비율이 제한을 초과합니다."
                        );
                    }
                    if (REQUIRED_DOCX_PARTS.contains(name)) {
                        selected.write(buffer, 0, read);
                    }
                }
                if (REQUIRED_DOCX_PARTS.contains(name)) {
                    required.put(name, selected.toByteArray());
                }
            }
        } catch (JobPostingFileException exception) {
            throw exception;
        } catch (IOException exception) {
            throw JobPostingFileException.unsupported("손상된 DOCX ZIP 구조입니다.");
        }
        return required;
    }

    private void validateImage(byte[] content, String expectedFormat) {
        if ("JPEG".equals(expectedFormat) && !hasJpegSignature(content)) {
            throw JobPostingFileException.unsupported("실제 JPEG 형식이 아닙니다.");
        }
        if ("PNG".equals(expectedFormat) && !startsWith(content, PNG_SIGNATURE)) {
            throw JobPostingFileException.unsupported("실제 PNG 형식이 아닙니다.");
        }
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(content))) {
            if (input == null) {
                throw JobPostingFileException.unsupported("이미지를 디코딩할 수 없습니다.");
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw JobPostingFileException.unsupported("지원되는 이미지 형식이 아닙니다.");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                String actualFormat = reader.getFormatName().toUpperCase(Locale.ROOT);
                if (!actualFormat.equals(expectedFormat)
                        && !("JPEG".equals(expectedFormat) && "JPG".equals(actualFormat))) {
                    throw JobPostingFileException.unsupported("이미지 확장자와 실제 형식이 다릅니다.");
                }
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                long pixels = Math.multiplyExact((long) width, (long) height);
                if (width < 1 || height < 1 || pixels > maxImagePixels) {
                    throw JobPostingFileException.unsupported(
                            "이미지 크기는 0보다 크고 총 %d픽셀 이하여야 합니다.".formatted(maxImagePixels)
                    );
                }
                BufferedImage decoded = reader.read(0);
                if (decoded == null) {
                    throw JobPostingFileException.unsupported("손상된 이미지입니다.");
                }
            } finally {
                reader.dispose();
            }
        } catch (ArithmeticException | IOException exception) {
            throw JobPostingFileException.unsupported("손상되었거나 지나치게 큰 이미지입니다.");
        }
    }

    private void validateHwp5(byte[] content) {
        if (!startsWith(content, CFB_SIGNATURE)) {
            throw JobPostingFileException.unsupported("실제 OLE2/CFB HWP 5.x 형식이 아닙니다.");
        }
        try (POIFSFileSystem fileSystem = new POIFSFileSystem(new ByteArrayInputStream(content))) {
            DirectoryEntry root = fileSystem.getRoot();
            Entry fileHeaderEntry = root.getEntry("FileHeader");
            if (!(fileHeaderEntry instanceof DocumentEntry documentEntry)) {
                throw JobPostingFileException.unsupported("HWP FileHeader가 없습니다.");
            }
            byte[] header;
            try (DocumentInputStream input = new DocumentInputStream(documentEntry)) {
                header = input.readNBytes(256);
            }
            if (header.length < 40) {
                throw JobPostingFileException.unsupported("HWP FileHeader가 손상되었습니다.");
            }
            String signature = new String(header, 0, 32, StandardCharsets.US_ASCII);
            if (!signature.startsWith("HWP Document File")) {
                throw JobPostingFileException.unsupported("HWP FileHeader 서명이 올바르지 않습니다.");
            }
            int majorVersion = Byte.toUnsignedInt(header[35]);
            if (majorVersion != 5) {
                throw JobPostingFileException.unsupported("HWP 5.x 문서만 허용합니다.");
            }
            int properties = littleEndianInt(header, 36);
            boolean encrypted = (properties & (1 << 1)) != 0;
            boolean distributable = (properties & (1 << 2)) != 0;
            if (encrypted || distributable) {
                throw JobPostingFileException.unsupported(
                        "암호화·비밀번호 보호 또는 배포용 HWP는 허용하지 않습니다."
                );
            }
            if (!root.hasEntry("DocInfo") || !root.hasEntry("BodyText")) {
                throw JobPostingFileException.unsupported("필수 HWP 5.x 문서 스트림이 없습니다.");
            }
        } catch (JobPostingFileException exception) {
            throw exception;
        } catch (IOException | RuntimeException exception) {
            throw JobPostingFileException.unsupported("손상되었거나 올바르지 않은 HWP 5.x 문서입니다.");
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
            throw JobPostingFileException.unsupported("손상된 DOCX XML 구조입니다.");
        }
    }

    private boolean isElement(Document document, String localName) {
        return localName.equalsIgnoreCase(document.getDocumentElement().getLocalName())
                || document.getDocumentElement().getNodeName().endsWith(":" + localName)
                || localName.equalsIgnoreCase(document.getDocumentElement().getNodeName());
    }

    private byte[] read(MultipartFile file) {
        try {
            return file.getBytes();
        } catch (IOException exception) {
            throw JobPostingFileException.invalid("업로드 파일을 읽을 수 없습니다.");
        }
    }

    private FilePolicy policy(String extension) {
        return switch (extension) {
            case "pdf" -> new FilePolicy(PDF_MIME, JobPostingFileFormat.PDF, Set.of(PDF_MIME));
            case "docx" -> new FilePolicy(DOCX_MIME, JobPostingFileFormat.DOCX, Set.of(DOCX_MIME));
            case "jpg", "jpeg" ->
                    new FilePolicy(JPEG_MIME, JobPostingFileFormat.JPEG, Set.of(JPEG_MIME));
            case "png" -> new FilePolicy(PNG_MIME, JobPostingFileFormat.PNG, Set.of(PNG_MIME));
            case "hwp" -> new FilePolicy(HWP5_MIME, JobPostingFileFormat.HWP5, HWP_REQUEST_MIMES);
            default -> throw JobPostingFileException.unsupported(
                    "PDF, DOCX, JPG, JPEG, PNG, HWP 5.x 파일만 허용합니다."
            );
        };
    }

    private void validateRequestedMime(FilePolicy policy, String contentType) {
        if (contentType == null
                || !policy.acceptedRequestMimes().contains(contentType.toLowerCase(Locale.ROOT))) {
            throw JobPostingFileException.unsupported("파일 MIME과 확장자가 일치하지 않습니다.");
        }
    }

    private String safeFileName(String originalFileName) {
        if (originalFileName == null || originalFileName.isBlank()) {
            throw JobPostingFileException.invalid("원본 파일명이 필요합니다.");
        }
        if (originalFileName.indexOf('\0') >= 0) {
            throw JobPostingFileException.invalid("파일명에 허용되지 않는 문자가 있습니다.");
        }
        try {
            String safeName = Path.of(originalFileName).getFileName().toString();
            safeName = Path.of(safeName.replace('\\', '/')).getFileName().toString();
            if (safeName.isBlank() || safeName.length() > MAX_FILE_NAME_LENGTH) {
                throw JobPostingFileException.invalid("파일명은 1자 이상 255자 이하여야 합니다.");
            }
            return safeName;
        } catch (InvalidPathException exception) {
            throw JobPostingFileException.invalid("올바르지 않은 파일명입니다.");
        }
    }

    private String extensionOf(String fileName) {
        int dot = fileName.lastIndexOf('.');
        if (dot < 1 || dot == fileName.length() - 1) {
            throw JobPostingFileException.unsupported("허용된 파일 확장자가 필요합니다.");
        }
        return fileName.substring(dot + 1).toLowerCase(Locale.ROOT);
    }

    private static boolean hasZipSignature(byte[] content) {
        return content.length >= 4
                && content[0] == 'P'
                && content[1] == 'K'
                && content[2] == 3
                && content[3] == 4;
    }

    private static boolean hasJpegSignature(byte[] content) {
        return content.length >= 3
                && content[0] == (byte) 0xFF
                && content[1] == (byte) 0xD8
                && content[2] == (byte) 0xFF;
    }

    private static boolean startsWith(byte[] content, byte[] signature) {
        if (content.length < signature.length) {
            return false;
        }
        for (int index = 0; index < signature.length; index++) {
            if (content[index] != signature[index]) {
                return false;
            }
        }
        return true;
    }

    private static int littleEndianInt(byte[] value, int offset) {
        return Byte.toUnsignedInt(value[offset])
                | (Byte.toUnsignedInt(value[offset + 1]) << 8)
                | (Byte.toUnsignedInt(value[offset + 2]) << 16)
                | (Byte.toUnsignedInt(value[offset + 3]) << 24);
    }

    private record FilePolicy(
            String normalizedMime,
            JobPostingFileFormat format,
            Set<String> acceptedRequestMimes
    ) {
    }
}
