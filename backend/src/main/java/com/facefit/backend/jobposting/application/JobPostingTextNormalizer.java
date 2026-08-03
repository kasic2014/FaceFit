package com.facefit.backend.jobposting.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.text.Normalizer;

@Component
public class JobPostingTextNormalizer {

    private final int maxCharacters;

    public JobPostingTextNormalizer(
            @Value("${facefit.job-postings.max-extracted-characters:50000}") int maxCharacters
    ) {
        this.maxCharacters = maxCharacters;
    }

    public String normalize(String value) {
        if (value == null) {
            return "";
        }
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC)
                .replace("\r\n", "\n")
                .replace('\r', '\n');
        StringBuilder safe = new StringBuilder(normalized.length());
        normalized.codePoints().forEach(codePoint -> {
            if (codePoint == '\n' || codePoint == '\t' || !Character.isISOControl(codePoint)) {
                safe.appendCodePoint(codePoint);
            }
        });
        normalized = safe.toString()
                .replaceAll("[\\t\\x0B\\f ]+", " ")
                .replaceAll(" *\\n *", "\n")
                .replaceAll("\\n{3,}", "\n\n")
                .strip();
        if (normalized.codePointCount(0, normalized.length()) > maxCharacters) {
            int end = normalized.offsetByCodePoints(0, maxCharacters);
            normalized = normalized.substring(0, end).stripTrailing();
        }
        return normalized;
    }
}
