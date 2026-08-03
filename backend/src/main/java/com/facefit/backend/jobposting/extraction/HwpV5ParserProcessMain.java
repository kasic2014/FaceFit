package com.facefit.backend.jobposting.extraction;

import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.parser.hwp.HwpV5Parser;
import org.apache.tika.sax.BodyContentHandler;
import org.apache.tika.sax.WriteOutContentHandler;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class HwpV5ParserProcessMain {

    static final int EXIT_SUCCESS = 0;
    static final int EXIT_PARSE_FAILED = 2;
    static final int EXIT_OUTPUT_LIMIT = 3;

    private HwpV5ParserProcessMain() {
    }

    public static void main(String[] arguments) {
        int exitCode = run(arguments);
        if (exitCode != EXIT_SUCCESS) {
            System.exit(exitCode);
        }
    }

    private static int run(String[] arguments) {
        if (arguments.length != 3) {
            return EXIT_PARSE_FAILED;
        }
        try {
            Path inputPath = Path.of(arguments[0]);
            Path outputPath = Path.of(arguments[1]);
            int maxCharacters = Integer.parseInt(arguments[2]);
            if (maxCharacters < 1 || !Files.isRegularFile(inputPath)) {
                return EXIT_PARSE_FAILED;
            }
            WriteOutContentHandler bounded = new WriteOutContentHandler(maxCharacters);
            BodyContentHandler handler = new BodyContentHandler(bounded);
            try (InputStream input = Files.newInputStream(inputPath)) {
                new HwpV5Parser().parse(
                        input,
                        handler,
                        new Metadata(),
                        new ParseContext()
                );
            }
            Files.writeString(
                    outputPath,
                    bounded.toString(),
                    StandardCharsets.UTF_8
            );
            return EXIT_SUCCESS;
        } catch (Exception exception) {
            if (exception.getClass().getName().contains("WriteLimitReachedException")) {
                return EXIT_OUTPUT_LIMIT;
            }
            return EXIT_PARSE_FAILED;
        }
    }
}
