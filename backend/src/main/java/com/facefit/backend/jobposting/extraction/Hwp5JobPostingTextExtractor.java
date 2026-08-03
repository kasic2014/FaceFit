package com.facefit.backend.jobposting.extraction;

import com.facefit.backend.jobposting.application.JobProcessingException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.jar.JarFile;

@Component
public class Hwp5JobPostingTextExtractor {

    private static final int MAX_UTF8_BYTES_PER_CODE_POINT = 4;
    private static final String CHILD_MAIN =
            "com.facefit.backend.jobposting.extraction.HwpV5ParserProcessMain";
    private static final String SPRING_BOOT_LAUNCHER =
            "org.springframework.boot.loader.launch.PropertiesLauncher";

    private final Duration timeout;
    private final int maxCharacters;
    private final int maxHeapMegabytes;

    public Hwp5JobPostingTextExtractor(
            @Value("${facefit.job-postings.hwp-timeout-seconds:30}") long timeoutSeconds,
            @Value("${facefit.job-postings.max-extracted-characters:50000}") int maxCharacters,
            @Value("${facefit.job-postings.hwp-max-heap-megabytes:256}") int maxHeapMegabytes
    ) {
        this.timeout = Duration.ofSeconds(timeoutSeconds);
        this.maxCharacters = maxCharacters;
        this.maxHeapMegabytes = Math.max(64, Math.min(maxHeapMegabytes, 512));
    }

    public String extract(byte[] content) {
        Path temporaryDirectory = null;
        Path input = null;
        Path output = null;
        Process process = null;
        try {
            temporaryDirectory = Files.createTempDirectory("facefit-hwp-" + UUID.randomUUID());
            input = temporaryDirectory.resolve(UUID.randomUUID() + ".hwp");
            output = temporaryDirectory.resolve(UUID.randomUUID() + ".txt");
            Files.write(input, content);

            process = new ProcessBuilder(command(input, output))
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .redirectError(ProcessBuilder.Redirect.DISCARD)
                    .start();
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new JobProcessingException("HWP_PARSE_TIMEOUT", true);
            }
            if (process.exitValue() == HwpV5ParserProcessMain.EXIT_OUTPUT_LIMIT) {
                throw new JobProcessingException("EXTRACTED_TEXT_TOO_LARGE", false);
            }
            if (process.exitValue() != HwpV5ParserProcessMain.EXIT_SUCCESS
                    || !Files.isRegularFile(output)) {
                throw new JobProcessingException("HWP_EXTRACTION_FAILED", false);
            }
            int maxOutputBytes = Math.multiplyExact(
                    maxCharacters,
                    MAX_UTF8_BYTES_PER_CODE_POINT
            );
            byte[] extracted = readBounded(output, maxOutputBytes);
            return new String(extracted, StandardCharsets.UTF_8);
        } catch (JobProcessingException exception) {
            throw exception;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            if (process != null) {
                process.destroyForcibly();
            }
            throw new JobProcessingException("HWP_PARSE_INTERRUPTED", true, exception);
        } catch (IOException | ArithmeticException exception) {
            if (process != null) {
                process.destroyForcibly();
            }
            throw new JobProcessingException("HWP_EXTRACTION_FAILED", false, exception);
        } finally {
            deleteQuietly(output);
            deleteQuietly(input);
            deleteQuietly(temporaryDirectory);
        }
    }

    private List<String> command(Path input, Path output) {
        String classpath = effectiveClasspath();
        List<String> command = new ArrayList<>();
        command.add(javaExecutable());
        command.add("-Xms32m");
        command.add("-Xmx" + maxHeapMegabytes + "m");
        command.add("-XX:MaxMetaspaceSize=128m");
        command.add("-Djava.awt.headless=true");
        if (isSpringBootExecutableJar(classpath)) {
            command.add("-Dloader.main=" + CHILD_MAIN);
            command.add("-cp");
            command.add(classpath);
            command.add(SPRING_BOOT_LAUNCHER);
        } else {
            command.add("-cp");
            command.add(classpath);
            command.add(CHILD_MAIN);
        }
        command.add(input.toString());
        command.add(output.toString());
        command.add(Integer.toString(maxCharacters));
        return List.copyOf(command);
    }

    private String effectiveClasspath() {
        String testClasspath = System.getProperty("surefire.test.class.path");
        if (testClasspath != null && !testClasspath.isBlank()) {
            return testClasspath;
        }
        String classpath = System.getProperty("java.class.path");
        if (classpath == null || classpath.isBlank()) {
            throw new JobProcessingException("HWP_PARSER_NOT_CONFIGURED", false);
        }
        return classpath;
    }

    private String javaExecutable() {
        String executable = System.getProperty("os.name", "")
                .toLowerCase()
                .contains("win") ? "java.exe" : "java";
        return Path.of(System.getProperty("java.home"), "bin", executable).toString();
    }

    private boolean isSpringBootExecutableJar(String classpath) {
        if (classpath.contains(File.pathSeparator)) {
            return false;
        }
        Path candidate;
        try {
            candidate = Path.of(classpath);
        } catch (RuntimeException exception) {
            return false;
        }
        if (!Files.isRegularFile(candidate)) {
            return false;
        }
        try (JarFile jar = new JarFile(candidate.toFile())) {
            return jar.getEntry("BOOT-INF/classes/" + CHILD_MAIN.replace('.', '/') + ".class")
                    != null;
        } catch (IOException exception) {
            return false;
        }
    }

    private byte[] readBounded(Path path, int maxBytes) throws IOException {
        try (var input = Files.newInputStream(path)) {
            byte[] content = input.readNBytes(maxBytes + 1);
            if (content.length > maxBytes) {
                throw new JobProcessingException("EXTRACTED_TEXT_TOO_LARGE", false);
            }
            return content;
        }
    }

    private void deleteQuietly(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // UUID-named temporary paths contain no user-provided names.
        }
    }
}
