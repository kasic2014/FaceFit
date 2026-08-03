package com.facefit.backend.jobposting.ocr;

import java.nio.file.Path;
import java.time.Duration;

public interface OcrCommandRunner {

    String run(Path inputImage, String languages, Duration timeout);
}
