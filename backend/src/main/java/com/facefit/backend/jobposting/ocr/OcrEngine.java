package com.facefit.backend.jobposting.ocr;

import java.awt.image.BufferedImage;

public interface OcrEngine {

    String recognize(BufferedImage image);
}
