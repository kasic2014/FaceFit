package com.facefit.backend.interview.application;

import com.facefit.backend.common.exception.InterviewProgressException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Set;

@Component
public class AnswerMediaValidator {

    public static final String MP4_MIME = "video/mp4";
    public static final String WEBM_MIME = "video/webm";
    public static final long MAX_FILE_BYTES = 200L * 1024 * 1024;
    public static final long MAX_DURATION_MILLIS = 300_000L;

    private static final int EBML_HEADER = 0x1A45DFA3;
    private static final int SEGMENT = 0x18538067;
    private static final int INFO = 0x1549A966;
    private static final int TIMECODE_SCALE = 0x2AD7B1;
    private static final int DURATION = 0x4489;
    private static final int TRACKS = 0x1654AE6B;
    private static final int TRACK_ENTRY = 0xAE;
    private static final int TRACK_TYPE = 0x83;
    private static final Set<Integer> WEBM_MASTER_IDS = Set.of(
            EBML_HEADER,
            SEGMENT,
            INFO,
            TRACKS,
            TRACK_ENTRY,
            0x1F43B675,
            0x114D9B74,
            0x1254C367
    );

    public ValidatedAnswerMedia validate(
            MultipartFile file,
            Integer recordedDurationSeconds
    ) {
        if (file == null || file.isEmpty()) {
            throw invalid("답변 영상 파일이 필요합니다.");
        }
        if (recordedDurationSeconds == null
                || recordedDurationSeconds < 1
                || recordedDurationSeconds > 300) {
            throw invalid("recordedDurationSec는 1 이상 300 이하여야 합니다.");
        }
        if (file.getSize() < 1 || file.getSize() > MAX_FILE_BYTES) {
            throw invalid("답변 영상은 200MB 이하여야 합니다.");
        }

        byte[] content;
        try {
            content = file.getBytes();
        } catch (IOException exception) {
            throw invalid("답변 영상을 읽을 수 없습니다.");
        }
        if (content.length < 1 || content.length > MAX_FILE_BYTES) {
            throw invalid("답변 영상은 200MB 이하여야 합니다.");
        }

        MediaInspection inspection;
        String extension;
        if (isMp4Signature(content)) {
            inspection = inspectMp4(content);
            extension = "mp4";
        } else if (isWebmSignature(content)) {
            inspection = inspectWebm(content);
            extension = "webm";
        } else {
            throw invalid("MP4 또는 WebM 영상만 업로드할 수 있습니다.");
        }

        String detectedMime = "mp4".equals(extension) ? MP4_MIME : WEBM_MIME;
        if (!detectedMime.equals(file.getContentType())) {
            throw invalid("Content-Type과 실제 영상 형식이 일치하지 않습니다.");
        }
        if (!inspection.videoTrack || !inspection.audioTrack) {
            throw invalid("영상 스트림과 음성 스트림이 모두 필요합니다.");
        }
        if (inspection.durationMillis < 1
                || inspection.durationMillis > MAX_DURATION_MILLIS) {
            throw invalid("답변 영상 길이는 5분 이하여야 합니다.");
        }

        return new ValidatedAnswerMedia(
                content,
                detectedMime,
                extension,
                content.length,
                sha256(content),
                inspection.durationMillis
        );
    }

    private MediaInspection inspectMp4(byte[] content) {
        Mp4Inspection inspection = new Mp4Inspection();
        walkMp4Boxes(content, 0, content.length, 0, inspection);
        if (!inspection.ftyp
                || !inspection.moov
                || inspection.durationMillis < 1) {
            throw invalid("손상되었거나 파싱할 수 없는 MP4 영상입니다.");
        }
        return new MediaInspection(
                inspection.videoTrack,
                inspection.audioTrack,
                inspection.durationMillis
        );
    }

    private void walkMp4Boxes(
            byte[] data,
            int start,
            int end,
            int depth,
            Mp4Inspection inspection
    ) {
        if (depth > 12) {
            throw invalid("MP4 컨테이너 구조가 올바르지 않습니다.");
        }
        int cursor = start;
        while (cursor + 8 <= end) {
            long size = unsignedInt(data, cursor);
            String type = ascii(data, cursor + 4, 4);
            int header = 8;
            if (size == 1) {
                if (cursor + 16 > end) {
                    throw invalid("MP4 box가 손상되었습니다.");
                }
                size = signedSafeLong(data, cursor + 8);
                header = 16;
            } else if (size == 0) {
                size = end - cursor;
            }
            if (size < header || size > end - cursor) {
                throw invalid("MP4 box 크기가 올바르지 않습니다.");
            }
            int contentStart = cursor + header;
            int boxEnd = cursor + (int) size;
            if ("ftyp".equals(type) && depth == 0) {
                inspection.ftyp = true;
            } else if ("moov".equals(type)) {
                inspection.moov = true;
            } else if ("mvhd".equals(type)) {
                inspection.durationMillis = parseMp4Duration(
                        data,
                        contentStart,
                        boxEnd
                );
            } else if ("hdlr".equals(type) && contentStart + 12 <= boxEnd) {
                String handler = ascii(data, contentStart + 8, 4);
                inspection.videoTrack |= "vide".equals(handler);
                inspection.audioTrack |= "soun".equals(handler);
            }

            if (isMp4Container(type)) {
                int childStart = contentStart + ("meta".equals(type) ? 4 : 0);
                if (childStart <= boxEnd) {
                    walkMp4Boxes(data, childStart, boxEnd, depth + 1, inspection);
                }
            }
            cursor = boxEnd;
        }
        if (cursor != end && end - cursor >= 8) {
            throw invalid("MP4 컨테이너 경계가 올바르지 않습니다.");
        }
    }

    private long parseMp4Duration(byte[] data, int start, int end) {
        if (start + 20 > end) {
            throw invalid("MP4 재생시간 정보를 읽을 수 없습니다.");
        }
        int version = data[start] & 0xff;
        long timescale;
        long duration;
        if (version == 0) {
            if (start + 20 > end) {
                throw invalid("MP4 재생시간 정보가 손상되었습니다.");
            }
            timescale = unsignedInt(data, start + 12);
            duration = unsignedInt(data, start + 16);
        } else if (version == 1) {
            if (start + 32 > end) {
                throw invalid("MP4 재생시간 정보가 손상되었습니다.");
            }
            timescale = unsignedInt(data, start + 20);
            duration = signedSafeLong(data, start + 24);
        } else {
            throw invalid("지원하지 않는 MP4 헤더 버전입니다.");
        }
        if (timescale < 1 || duration < 1) {
            throw invalid("MP4 재생시간이 올바르지 않습니다.");
        }
        double millis = (duration * 1000.0d) / timescale;
        if (!Double.isFinite(millis) || millis > Long.MAX_VALUE) {
            throw invalid("MP4 재생시간이 올바르지 않습니다.");
        }
        return Math.round(millis);
    }

    private MediaInspection inspectWebm(byte[] content) {
        WebmInspection inspection = new WebmInspection();
        parseWebmElements(content, 0, content.length, 0, inspection);
        if (!inspection.ebml
                || !inspection.segment
                || inspection.durationUnits == null) {
            throw invalid("손상되었거나 파싱할 수 없는 WebM 영상입니다.");
        }
        double millis = inspection.durationUnits
                * inspection.timecodeScale
                / 1_000_000.0d;
        if (!Double.isFinite(millis) || millis < 1 || millis > Long.MAX_VALUE) {
            throw invalid("WebM 재생시간이 올바르지 않습니다.");
        }
        return new MediaInspection(
                inspection.videoTrack,
                inspection.audioTrack,
                Math.round(millis)
        );
    }

    private void parseWebmElements(
            byte[] data,
            int start,
            int end,
            int depth,
            WebmInspection inspection
    ) {
        if (depth > 12) {
            throw invalid("WebM 컨테이너 구조가 올바르지 않습니다.");
        }
        int cursor = start;
        while (cursor < end) {
            Vint id = readVint(data, cursor, end, true);
            Vint size = readVint(data, cursor + id.length, end, false);
            int payloadStart = cursor + id.length + size.length;
            long available = end - payloadStart;
            long payloadSize = size.unknown ? available : size.value;
            if (payloadSize < 0 || payloadSize > available || payloadSize > Integer.MAX_VALUE) {
                throw invalid("WebM element 크기가 올바르지 않습니다.");
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
            if (size.unknown) {
                break;
            }
        }
    }

    private Vint readVint(byte[] data, int offset, int end, boolean keepMarker) {
        if (offset >= end) {
            throw invalid("WebM VINT가 손상되었습니다.");
        }
        int first = data[offset] & 0xff;
        int mask = 0x80;
        int length = 1;
        while (length <= 8 && (first & mask) == 0) {
            mask >>>= 1;
            length++;
        }
        if (length > 8 || offset + length > end) {
            throw invalid("WebM VINT가 손상되었습니다.");
        }
        long value = keepMarker ? first : first & (mask - 1);
        boolean unknown = !keepMarker && value == mask - 1;
        for (int index = 1; index < length; index++) {
            int next = data[offset + index] & 0xff;
            value = (value << 8) | next;
            unknown &= next == 0xff;
        }
        return new Vint(value, length, unknown);
    }

    private long readUnsigned(byte[] data, int start, int end) {
        int length = end - start;
        if (length < 1 || length > 8) {
            throw invalid("WebM 정수 값이 올바르지 않습니다.");
        }
        long value = 0;
        for (int index = start; index < end; index++) {
            if (value > (Long.MAX_VALUE >>> 8)) {
                throw invalid("WebM 정수 값이 너무 큽니다.");
            }
            value = (value << 8) | (data[index] & 0xffL);
        }
        return value;
    }

    private double readFloat(byte[] data, int start, int end) {
        int length = end - start;
        if (length == 4) {
            return Float.intBitsToFloat((int) unsignedInt(data, start));
        }
        if (length == 8) {
            return Double.longBitsToDouble(signedSafeLong(data, start));
        }
        throw invalid("WebM Duration 형식이 올바르지 않습니다.");
    }

    private boolean isMp4Signature(byte[] content) {
        return content.length >= 12 && "ftyp".equals(ascii(content, 4, 4));
    }

    private boolean isWebmSignature(byte[] content) {
        return content.length >= 4
                && (content[0] & 0xff) == 0x1a
                && (content[1] & 0xff) == 0x45
                && (content[2] & 0xff) == 0xdf
                && (content[3] & 0xff) == 0xa3;
    }

    private boolean isMp4Container(String type) {
        return Set.of(
                "moov", "trak", "mdia", "minf", "stbl", "edts", "udta", "meta"
        ).contains(type);
    }

    private long unsignedInt(byte[] data, int offset) {
        if (offset < 0 || offset + 4 > data.length) {
            throw invalid("미디어 정수 경계가 올바르지 않습니다.");
        }
        return ((data[offset] & 0xffL) << 24)
                | ((data[offset + 1] & 0xffL) << 16)
                | ((data[offset + 2] & 0xffL) << 8)
                | (data[offset + 3] & 0xffL);
    }

    private long signedSafeLong(byte[] data, int offset) {
        if (offset < 0 || offset + 8 > data.length || (data[offset] & 0x80) != 0) {
            throw invalid("미디어 정수 값이 너무 큽니다.");
        }
        long value = 0;
        for (int index = 0; index < 8; index++) {
            value = (value << 8) | (data[offset + index] & 0xffL);
        }
        return value;
    }

    private String ascii(byte[] data, int offset, int length) {
        if (offset < 0 || offset + length > data.length) {
            return "";
        }
        return new String(data, offset, length, StandardCharsets.US_ASCII);
    }

    private String sha256(byte[] content) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(content)
            );
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", impossible);
        }
    }

    private InterviewProgressException invalid(String message) {
        return new InterviewProgressException(
                HttpStatus.BAD_REQUEST,
                "INVALID_ANSWER_MEDIA",
                message
        );
    }

    private record MediaInspection(
            boolean videoTrack,
            boolean audioTrack,
            long durationMillis
    ) {
    }

    private record Vint(long value, int length, boolean unknown) {
    }

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
