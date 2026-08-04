package com.facefit.backend.interview.application;

import com.facefit.backend.common.exception.InterviewProgressException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;

@Component
public class AnswerMediaValidator {

    public static final String MP4_MIME = "video/mp4";
    public static final String WEBM_MIME = "video/webm";
    public static final long MAX_FILE_BYTES = 200L * 1024 * 1024;
    public static final long MAX_DURATION_MILLIS = 300_000L;

    private static final int EBML_HEADER = 0x1A45DFA3;
    private static final int SEGMENT = 0x18538067;
    private static final int TIMECODE_SCALE = 0x2AD7B1;
    private static final int DURATION = 0x4489;
    private static final int TRACK_TYPE = 0x83;
    private static final Set<Integer> WEBM_MASTER_IDS = Set.of(
            EBML_HEADER, SEGMENT, 0x1549A966, 0x1654AE6B, 0xAE,
            0x1F43B675, 0x114D9B74, 0x1254C367
    );
    private static final Set<String> MP4_CONTAINERS = Set.of(
            "moov", "trak", "mdia", "minf", "stbl", "edts", "udta", "meta"
    );

    private final Path tempDirectory;

    public AnswerMediaValidator(
            @Value("${facefit.storage.interview-answers.temp-directory:${java.io.tmpdir}/facefit-answers}")
            Path tempDirectory
    ) {
        this.tempDirectory = tempDirectory;
    }

    public ValidatedAnswerMedia validate(MultipartFile file, Integer recordedDurationSeconds) {
        if (file == null || file.isEmpty()) {
            throw invalid("Answer media is required.");
        }
        if (recordedDurationSeconds == null
                || recordedDurationSeconds < 1
                || recordedDurationSeconds > 300) {
            throw invalid("recordedDurationSec must be between 1 and 300.");
        }
        if (file.getSize() < 1 || file.getSize() > MAX_FILE_BYTES) {
            throw invalid("Answer media must not exceed 200MB.");
        }

        Path requestDirectory = null;
        Path path = null;
        try {
            Files.createDirectories(tempDirectory);
            requestDirectory = Files.createDirectory(
                    tempDirectory.resolve("request-" + UUID.randomUUID())
            );
            path = requestDirectory.resolve("media.bin");
            MessageDigest digest = sha256Digest();
            long size = copyBounded(file, path, digest);
            if (size < 1) {
                throw invalid("Answer media is empty.");
            }

            MediaInspection inspection;
            String extension;
            try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
                ByteBuffer data = channel.map(FileChannel.MapMode.READ_ONLY, 0, size);
                if (isMp4Signature(data)) {
                    inspection = inspectMp4(data);
                    extension = "mp4";
                } else if (isWebmSignature(data)) {
                    inspection = inspectWebm(data);
                    extension = "webm";
                } else {
                    throw invalid("Only MP4 or WebM media is supported.");
                }
            }

            String mimeType = "mp4".equals(extension) ? MP4_MIME : WEBM_MIME;
            if (!mimeType.equals(file.getContentType())) {
                throw invalid("Content-Type does not match the media container.");
            }
            if (!inspection.videoTrack || !inspection.audioTrack) {
                throw invalid("Both video and audio tracks are required.");
            }
            if (inspection.durationMillis < 1
                    || inspection.durationMillis > MAX_DURATION_MILLIS) {
                throw invalid("Answer media duration must not exceed 300 seconds.");
            }
            return new ValidatedAnswerMedia(
                    path, mimeType, extension, size,
                    HexFormat.of().formatHex(digest.digest()),
                    inspection.durationMillis
            );
        } catch (IOException exception) {
            cleanup(path, requestDirectory);
            throw invalid("Answer media could not be read.");
        } catch (RuntimeException exception) {
            cleanup(path, requestDirectory);
            throw exception;
        }
    }

    private long copyBounded(MultipartFile file, Path path, MessageDigest digest)
            throws IOException {
        long total = 0;
        try (InputStream source = file.getInputStream();
             OutputStream destination = Files.newOutputStream(
                     path, StandardOpenOption.CREATE_NEW
             )) {
            byte[] chunk = new byte[1024 * 1024];
            int read;
            while ((read = source.read(chunk)) != -1) {
                total += read;
                if (total > MAX_FILE_BYTES) {
                    throw invalid("Answer media must not exceed 200MB.");
                }
                digest.update(chunk, 0, read);
                destination.write(chunk, 0, read);
            }
        }
        return total;
    }

    private MediaInspection inspectMp4(ByteBuffer data) {
        Mp4Inspection inspection = new Mp4Inspection();
        walkMp4Boxes(data, 0, data.limit(), 0, inspection);
        if (!inspection.ftyp || !inspection.moov || inspection.durationMillis < 1) {
            throw invalid("The MP4 container is invalid or unsupported.");
        }
        return new MediaInspection(
                inspection.videoTrack, inspection.audioTrack, inspection.durationMillis
        );
    }

    private void walkMp4Boxes(ByteBuffer data, int start, int end, int depth,
                              Mp4Inspection inspection) {
        if (depth > 12) {
            throw invalid("The MP4 container nesting is invalid.");
        }
        int cursor = start;
        while (cursor + 8 <= end) {
            long size = unsignedInt(data, cursor);
            String type = ascii(data, cursor + 4, 4);
            int header = 8;
            if (size == 1) {
                if (cursor + 16 > end) throw invalid("The MP4 box is truncated.");
                size = signedSafeLong(data, cursor + 8);
                header = 16;
            } else if (size == 0) {
                size = end - cursor;
            }
            if (size < header || size > end - cursor) {
                throw invalid("The MP4 box size is invalid.");
            }
            int contentStart = cursor + header;
            int boxEnd = cursor + (int) size;
            if ("ftyp".equals(type) && depth == 0) inspection.ftyp = true;
            else if ("moov".equals(type)) inspection.moov = true;
            else if ("mvhd".equals(type)) {
                inspection.durationMillis = parseMp4Duration(data, contentStart, boxEnd);
            } else if ("hdlr".equals(type) && contentStart + 12 <= boxEnd) {
                String handler = ascii(data, contentStart + 8, 4);
                inspection.videoTrack |= "vide".equals(handler);
                inspection.audioTrack |= "soun".equals(handler);
            }
            if (MP4_CONTAINERS.contains(type)) {
                int childStart = contentStart + ("meta".equals(type) ? 4 : 0);
                if (childStart <= boxEnd) {
                    walkMp4Boxes(data, childStart, boxEnd, depth + 1, inspection);
                }
            }
            cursor = boxEnd;
        }
    }

    private long parseMp4Duration(ByteBuffer data, int start, int end) {
        if (start + 20 > end) throw invalid("MP4 duration metadata is invalid.");
        int version = data.get(start) & 0xff;
        long timescale;
        long duration;
        if (version == 0) {
            timescale = unsignedInt(data, start + 12);
            duration = unsignedInt(data, start + 16);
        } else if (version == 1 && start + 32 <= end) {
            timescale = unsignedInt(data, start + 20);
            duration = signedSafeLong(data, start + 24);
        } else {
            throw invalid("MP4 duration metadata is unsupported.");
        }
        if (timescale < 1 || duration < 1) throw invalid("MP4 duration is invalid.");
        double millis = duration * 1000.0d / timescale;
        if (!Double.isFinite(millis) || millis > Long.MAX_VALUE) {
            throw invalid("MP4 duration is invalid.");
        }
        return Math.round(millis);
    }

    private MediaInspection inspectWebm(ByteBuffer data) {
        WebmInspection inspection = new WebmInspection();
        parseWebmElements(data, 0, data.limit(), 0, inspection);
        if (!inspection.ebml || !inspection.segment || inspection.durationUnits == null) {
            throw invalid("The WebM container is invalid or unsupported.");
        }
        double millis = inspection.durationUnits * inspection.timecodeScale / 1_000_000.0d;
        if (!Double.isFinite(millis) || millis < 1 || millis > Long.MAX_VALUE) {
            throw invalid("WebM duration is invalid.");
        }
        return new MediaInspection(
                inspection.videoTrack, inspection.audioTrack, Math.round(millis)
        );
    }

    private void parseWebmElements(ByteBuffer data, int start, int end, int depth,
                                   WebmInspection inspection) {
        if (depth > 12) throw invalid("The WebM container nesting is invalid.");
        int cursor = start;
        while (cursor < end) {
            Vint id = readVint(data, cursor, end, true);
            Vint size = readVint(data, cursor + id.length, end, false);
            int payloadStart = cursor + id.length + size.length;
            long available = end - payloadStart;
            long payloadSize = size.unknown ? available : size.value;
            if (payloadSize < 0 || payloadSize > available || payloadSize > Integer.MAX_VALUE) {
                throw invalid("The WebM element size is invalid.");
            }
            int payloadEnd = payloadStart + (int) payloadSize;
            int elementId = (int) id.value;
            inspection.ebml |= elementId == EBML_HEADER;
            inspection.segment |= elementId == SEGMENT;
            if (elementId == TIMECODE_SCALE) {
                inspection.timecodeScale = readUnsigned(data, payloadStart, payloadEnd);
            } else if (elementId == DURATION) {
                inspection.durationUnits = readFloat(data, payloadStart, payloadEnd);
            } else if (elementId == TRACK_TYPE) {
                long type = readUnsigned(data, payloadStart, payloadEnd);
                inspection.videoTrack |= type == 1;
                inspection.audioTrack |= type == 2;
            }
            if (WEBM_MASTER_IDS.contains(elementId)) {
                parseWebmElements(data, payloadStart, payloadEnd, depth + 1, inspection);
            }
            cursor = payloadEnd;
            if (size.unknown) break;
        }
    }

    private Vint readVint(ByteBuffer data, int offset, int end, boolean keepMarker) {
        if (offset >= end) throw invalid("The WebM VINT is invalid.");
        int first = data.get(offset) & 0xff;
        int mask = 0x80;
        int length = 1;
        while (length <= 8 && (first & mask) == 0) {
            mask >>>= 1;
            length++;
        }
        if (length > 8 || offset + length > end) throw invalid("The WebM VINT is invalid.");
        long value = keepMarker ? first : first & (mask - 1);
        boolean unknown = !keepMarker && value == mask - 1;
        for (int index = 1; index < length; index++) {
            int next = data.get(offset + index) & 0xff;
            value = (value << 8) | next;
            unknown &= next == 0xff;
        }
        return new Vint(value, length, unknown);
    }

    private long readUnsigned(ByteBuffer data, int start, int end) {
        int length = end - start;
        if (length < 1 || length > 8) throw invalid("The WebM integer is invalid.");
        long value = 0;
        for (int index = start; index < end; index++) {
            if (value > (Long.MAX_VALUE >>> 8)) throw invalid("The WebM integer is too large.");
            value = (value << 8) | (data.get(index) & 0xffL);
        }
        return value;
    }

    private double readFloat(ByteBuffer data, int start, int end) {
        int length = end - start;
        if (length == 4) return Float.intBitsToFloat((int) unsignedInt(data, start));
        if (length == 8) return Double.longBitsToDouble(signedSafeLong(data, start));
        throw invalid("The WebM duration format is invalid.");
    }

    private boolean isMp4Signature(ByteBuffer data) {
        return data.limit() >= 12 && "ftyp".equals(ascii(data, 4, 4));
    }

    private boolean isWebmSignature(ByteBuffer data) {
        return data.limit() >= 4
                && (data.get(0) & 0xff) == 0x1a
                && (data.get(1) & 0xff) == 0x45
                && (data.get(2) & 0xff) == 0xdf
                && (data.get(3) & 0xff) == 0xa3;
    }

    private long unsignedInt(ByteBuffer data, int offset) {
        if (offset < 0 || offset + 4 > data.limit()) throw invalid("Media integer boundary is invalid.");
        return ((data.get(offset) & 0xffL) << 24)
                | ((data.get(offset + 1) & 0xffL) << 16)
                | ((data.get(offset + 2) & 0xffL) << 8)
                | (data.get(offset + 3) & 0xffL);
    }

    private long signedSafeLong(ByteBuffer data, int offset) {
        if (offset < 0 || offset + 8 > data.limit() || (data.get(offset) & 0x80) != 0) {
            throw invalid("Media integer is too large.");
        }
        long value = 0;
        for (int index = 0; index < 8; index++) {
            value = (value << 8) | (data.get(offset + index) & 0xffL);
        }
        return value;
    }

    private String ascii(ByteBuffer data, int offset, int length) {
        if (offset < 0 || offset + length > data.limit()) return "";
        byte[] value = new byte[length];
        for (int index = 0; index < length; index++) value[index] = data.get(offset + index);
        return new String(value, StandardCharsets.US_ASCII);
    }

    private MessageDigest sha256Digest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable.", impossible);
        }
    }

    private void cleanup(Path path, Path directory) {
        try {
            if (path != null) Files.deleteIfExists(path);
            if (directory != null) Files.deleteIfExists(directory);
        } catch (IOException ignored) {
            // Best effort; never expose a local path in the error response.
        }
    }

    private InterviewProgressException invalid(String message) {
        return new InterviewProgressException(
                HttpStatus.BAD_REQUEST, "INVALID_ANSWER_MEDIA", message
        );
    }

    private record MediaInspection(boolean videoTrack, boolean audioTrack, long durationMillis) {}
    private record Vint(long value, int length, boolean unknown) {}
    private static final class Mp4Inspection {
        private boolean ftyp;
        private boolean moov;
        private boolean videoTrack;
        private boolean audioTrack;
        private long durationMillis;
    }
    private static final class WebmInspection {
        private boolean ebml;
        private boolean segment;
        private boolean videoTrack;
        private boolean audioTrack;
        private long timecodeScale = 1_000_000L;
        private Double durationUnits;
    }
}
