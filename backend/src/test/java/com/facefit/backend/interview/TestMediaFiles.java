package com.facefit.backend.interview;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

final class TestMediaFiles {

    private TestMediaFiles() {
    }

    static byte[] mp4(boolean video, boolean audio, int durationSeconds) {
        byte[] ftyp = box(
                "ftyp",
                "isom\u0000\u0000\u0002\u0000isom".getBytes(StandardCharsets.ISO_8859_1)
        );
        ByteBuffer mvhd = ByteBuffer.allocate(20);
        mvhd.putInt(0);
        mvhd.putInt(0);
        mvhd.putInt(0);
        mvhd.putInt(1_000);
        mvhd.putInt(durationSeconds * 1_000);

        ByteArrayOutputStream moov = new ByteArrayOutputStream();
        moov.writeBytes(box("mvhd", mvhd.array()));
        if (video) {
            moov.writeBytes(track("vide"));
        }
        if (audio) {
            moov.writeBytes(track("soun"));
        }
        ByteArrayOutputStream file = new ByteArrayOutputStream();
        file.writeBytes(ftyp);
        file.writeBytes(box("moov", moov.toByteArray()));
        return file.toByteArray();
    }

    static byte[] webm(boolean video, boolean audio, double durationSeconds) {
        byte[] timecodeScale = element(
                new byte[]{0x2a, (byte) 0xd7, (byte) 0xb1},
                new byte[]{0x0f, 0x42, 0x40}
        );
        byte[] duration = element(
                new byte[]{0x44, (byte) 0x89},
                ByteBuffer.allocate(8).putDouble(durationSeconds * 1_000).array()
        );
        byte[] info = element(
                new byte[]{0x15, 0x49, (byte) 0xa9, 0x66},
                concat(timecodeScale, duration)
        );
        ByteArrayOutputStream tracks = new ByteArrayOutputStream();
        if (video) {
            tracks.writeBytes(element(
                    new byte[]{(byte) 0xae},
                    element(new byte[]{(byte) 0x83}, new byte[]{0x01})
            ));
        }
        if (audio) {
            tracks.writeBytes(element(
                    new byte[]{(byte) 0xae},
                    element(new byte[]{(byte) 0x83}, new byte[]{0x02})
            ));
        }
        byte[] tracksElement = element(
                new byte[]{0x16, 0x54, (byte) 0xae, 0x6b},
                tracks.toByteArray()
        );
        byte[] segment = element(
                new byte[]{0x18, 0x53, (byte) 0x80, 0x67},
                concat(info, tracksElement)
        );
        byte[] ebml = element(
                new byte[]{0x1a, 0x45, (byte) 0xdf, (byte) 0xa3},
                new byte[0]
        );
        return concat(ebml, segment);
    }

    private static byte[] track(String handler) {
        ByteBuffer hdlr = ByteBuffer.allocate(12);
        hdlr.putInt(0);
        hdlr.putInt(0);
        hdlr.put(handler.getBytes(StandardCharsets.US_ASCII));
        return box("trak", box("mdia", box("hdlr", hdlr.array())));
    }

    private static byte[] box(String type, byte[] payload) {
        ByteBuffer result = ByteBuffer.allocate(8 + payload.length);
        result.putInt(8 + payload.length);
        result.put(type.getBytes(StandardCharsets.US_ASCII));
        result.put(payload);
        return result.array();
    }

    private static byte[] element(byte[] id, byte[] payload) {
        if (payload.length > 126) {
            throw new IllegalArgumentException("테스트 EBML payload가 너무 큽니다.");
        }
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        result.writeBytes(id);
        result.write(0x80 | payload.length);
        result.writeBytes(payload);
        return result.toByteArray();
    }

    private static byte[] concat(byte[]... values) {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        for (byte[] value : values) {
            result.writeBytes(value);
        }
        return result.toByteArray();
    }
}
