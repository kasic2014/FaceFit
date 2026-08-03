package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.application.JobProcessingException;
import com.facefit.backend.jobposting.ocr.ExifOrientationNormalizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.Iterator;

@Component
public class SafeImageDecoder {

    private final long maxPixels;
    private final ExifOrientationNormalizer orientationNormalizer;

    public SafeImageDecoder(
            @Value("${facefit.job-postings.max-image-pixels:40000000}") long maxPixels,
            ExifOrientationNormalizer orientationNormalizer
    ) {
        this.maxPixels = maxPixels;
        this.orientationNormalizer = orientationNormalizer;
    }

    public BufferedImage decode(byte[] content, boolean normalizeExif) {
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(content))) {
            if (input == null) {
                throw new JobProcessingException("IMAGE_DECODE_FAILED", false);
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new JobProcessingException("IMAGE_DECODE_FAILED", false);
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                long pixels = Math.multiplyExact((long) width, (long) height);
                if (width < 1 || height < 1 || pixels > maxPixels) {
                    throw new JobProcessingException("IMAGE_PIXEL_LIMIT_EXCEEDED", false);
                }
                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw new JobProcessingException("IMAGE_DECODE_FAILED", false);
                }
                return normalizeExif ? orientationNormalizer.normalize(content, image) : image;
            } finally {
                reader.dispose();
            }
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (ArithmeticException | IOException exception) {
            throw new JobProcessingException("IMAGE_DECODE_FAILED", false, exception);
        }
    }
}
