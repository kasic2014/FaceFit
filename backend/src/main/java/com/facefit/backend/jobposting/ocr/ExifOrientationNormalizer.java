package com.facefit.backend.jobposting.ocr;

import org.springframework.stereotype.Component;

import java.awt.Graphics2D;
import java.awt.geom.AffineTransform;
import java.awt.image.BufferedImage;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

@Component
public class ExifOrientationNormalizer {

    public BufferedImage normalize(byte[] original, BufferedImage image) {
        int orientation = readJpegExifOrientation(original);
        if (orientation < 2 || orientation > 8) {
            return image;
        }
        int width = image.getWidth();
        int height = image.getHeight();
        boolean swapDimensions = orientation >= 5 && orientation <= 8;
        BufferedImage result = new BufferedImage(
                swapDimensions ? height : width,
                swapDimensions ? width : height,
                BufferedImage.TYPE_INT_RGB
        );
        AffineTransform transform = transform(orientation, width, height);
        Graphics2D graphics = result.createGraphics();
        try {
            graphics.drawImage(image, transform, null);
        } finally {
            graphics.dispose();
        }
        return result;
    }

    private AffineTransform transform(int orientation, int width, int height) {
        AffineTransform transform = new AffineTransform();
        switch (orientation) {
            case 2 -> {
                transform.translate(width, 0);
                transform.scale(-1, 1);
            }
            case 3 -> {
                transform.translate(width, height);
                transform.rotate(Math.PI);
            }
            case 4 -> {
                transform.translate(0, height);
                transform.scale(1, -1);
            }
            case 5 -> {
                transform.rotate(Math.PI / 2);
                transform.scale(1, -1);
            }
            case 6 -> {
                transform.translate(height, 0);
                transform.rotate(Math.PI / 2);
            }
            case 7 -> {
                transform.translate(height, width);
                transform.scale(-1, 1);
                transform.rotate(3 * Math.PI / 2);
            }
            case 8 -> {
                transform.translate(0, width);
                transform.rotate(3 * Math.PI / 2);
            }
            default -> {
            }
        }
        return transform;
    }

    private int readJpegExifOrientation(byte[] data) {
        if (data.length < 4
                || data[0] != (byte) 0xFF
                || data[1] != (byte) 0xD8) {
            return 1;
        }
        int offset = 2;
        while (offset + 4 <= data.length) {
            if (data[offset] != (byte) 0xFF) {
                return 1;
            }
            int marker = Byte.toUnsignedInt(data[offset + 1]);
            offset += 2;
            if (marker == 0xDA || marker == 0xD9) {
                break;
            }
            int length = unsignedShort(data, offset, ByteOrder.BIG_ENDIAN);
            if (length < 2 || offset + length > data.length) {
                return 1;
            }
            if (marker == 0xE1
                    && length >= 14
                    && data[offset + 2] == 'E'
                    && data[offset + 3] == 'x'
                    && data[offset + 4] == 'i'
                    && data[offset + 5] == 'f') {
                return parseTiffOrientation(data, offset + 8, length - 8);
            }
            offset += length;
        }
        return 1;
    }

    private int parseTiffOrientation(byte[] data, int tiffStart, int available) {
        if (available < 8 || tiffStart + available > data.length) {
            return 1;
        }
        ByteOrder order;
        if (data[tiffStart] == 'I' && data[tiffStart + 1] == 'I') {
            order = ByteOrder.LITTLE_ENDIAN;
        } else if (data[tiffStart] == 'M' && data[tiffStart + 1] == 'M') {
            order = ByteOrder.BIG_ENDIAN;
        } else {
            return 1;
        }
        ByteBuffer buffer = ByteBuffer.wrap(data).order(order);
        int ifdOffset = buffer.getInt(tiffStart + 4);
        int ifd = tiffStart + ifdOffset;
        if (ifd < tiffStart || ifd + 2 > tiffStart + available) {
            return 1;
        }
        int entries = Short.toUnsignedInt(buffer.getShort(ifd));
        for (int index = 0; index < entries; index++) {
            int entry = ifd + 2 + index * 12;
            if (entry + 12 > tiffStart + available) {
                return 1;
            }
            if (Short.toUnsignedInt(buffer.getShort(entry)) == 0x0112) {
                return Short.toUnsignedInt(buffer.getShort(entry + 8));
            }
        }
        return 1;
    }

    private int unsignedShort(byte[] data, int offset, ByteOrder order) {
        if (offset + 2 > data.length) {
            return -1;
        }
        return Short.toUnsignedInt(ByteBuffer.wrap(data, offset, 2).order(order).getShort());
    }
}
