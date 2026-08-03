package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.ocr.OcrEngine;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class ImageJobPostingTextExtractor {

    private final SafeImageDecoder imageDecoder;
    private final OcrEngine ocrEngine;

    public String extract(byte[] content) {
        return ocrEngine.recognize(imageDecoder.decode(content, true));
    }
}
