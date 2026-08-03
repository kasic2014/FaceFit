package com.facefit.backend.jobposting.application;

import com.facefit.backend.jobposting.domain.StructuredJobPosting;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Component
public class DeterministicJobPostingStructurer {

    private static final int SHORT_FIELD_LIMIT = 500;
    private static final int LONG_FIELD_LIMIT = 10_000;
    private static final List<Alias> ALIASES = aliases();

    public StructuredJobPosting structure(String text) {
        Map<Field, List<String>> sections = new EnumMap<>(Field.class);
        Field currentField = null;
        for (String rawLine : text.split("\\n", -1)) {
            String line = stripLineDecoration(rawLine);
            Header header = header(line);
            if (header != null) {
                currentField = header.field();
                if (!header.inlineValue().isBlank()) {
                    sections.computeIfAbsent(currentField, ignored -> new ArrayList<>())
                            .add(header.inlineValue());
                }
                continue;
            }
            if (currentField != null && !line.isBlank()) {
                sections.computeIfAbsent(currentField, ignored -> new ArrayList<>()).add(line);
            }
        }

        return new StructuredJobPosting(
                value(sections, Field.COMPANY_NAME, SHORT_FIELD_LIMIT),
                value(sections, Field.TARGET_ROLE, SHORT_FIELD_LIMIT),
                value(sections, Field.MAIN_RESPONSIBILITIES, LONG_FIELD_LIMIT),
                value(sections, Field.QUALIFICATIONS, LONG_FIELD_LIMIT),
                value(sections, Field.PREFERRED_QUALIFICATIONS, LONG_FIELD_LIMIT),
                value(sections, Field.TECHNOLOGIES_TOOLS, LONG_FIELD_LIMIT),
                value(sections, Field.CORE_COMPETENCIES, LONG_FIELD_LIMIT),
                value(sections, Field.COMPANY_BUSINESS_INTRO, LONG_FIELD_LIMIT)
        );
    }

    private Header header(String line) {
        String comparable = line.toLowerCase(Locale.ROOT);
        for (Alias alias : ALIASES) {
            String title = alias.title().toLowerCase(Locale.ROOT);
            if (comparable.equals(title)) {
                return new Header(alias.field(), "");
            }
            if (!comparable.startsWith(title) || comparable.length() == title.length()) {
                continue;
            }
            char delimiter = comparable.charAt(title.length());
            if (delimiter == ':' || delimiter == '：' || delimiter == '-' || Character.isWhitespace(delimiter)) {
                String inline = line.substring(title.length() + 1)
                        .replaceFirst("^[\\s:：\\-–—]+", "")
                        .strip();
                return new Header(alias.field(), inline);
            }
        }
        return null;
    }

    private String value(Map<Field, List<String>> sections, Field field, int maxLength) {
        List<String> values = sections.get(field);
        if (values == null || values.isEmpty()) {
            return null;
        }
        Set<String> unique = new LinkedHashSet<>();
        values.stream()
                .map(String::strip)
                .filter(value -> !value.isBlank())
                .forEach(unique::add);
        if (unique.isEmpty()) {
            return null;
        }
        String joined = String.join("\n", unique);
        if (joined.codePointCount(0, joined.length()) <= maxLength) {
            return joined;
        }
        return joined.substring(0, joined.offsetByCodePoints(0, maxLength)).stripTrailing();
    }

    private String stripLineDecoration(String value) {
        return value.replaceFirst("^[\\s#>*•·▪◦\\-–—]+", "").strip();
    }

    private static List<Alias> aliases() {
        List<Alias> aliases = new ArrayList<>();
        add(aliases, Field.COMPANY_NAME, "회사명", "기업명", "채용 기업");
        add(aliases, Field.TARGET_ROLE, "모집 직무", "채용 직무", "모집 분야", "포지션", "직무");
        add(aliases, Field.MAIN_RESPONSIBILITIES, "주요 업무", "담당 업무", "업무 내용", "수행 업무");
        add(aliases, Field.QUALIFICATIONS, "자격요건", "자격 요건", "지원 자격", "필수 사항");
        add(aliases, Field.PREFERRED_QUALIFICATIONS, "우대사항", "우대 사항", "우대 조건");
        add(aliases, Field.TECHNOLOGIES_TOOLS, "기술 스택", "사용 기술", "개발 환경", "도구");
        add(aliases, Field.CORE_COMPETENCIES, "핵심 역량", "필요 역량");
        add(aliases, Field.COMPANY_BUSINESS_INTRO, "회사 소개", "기업 소개", "사업 소개");
        aliases.sort(Comparator.comparingInt((Alias alias) -> alias.title().length()).reversed());
        return List.copyOf(aliases);
    }

    private static void add(List<Alias> aliases, Field field, String... titles) {
        for (String title : titles) {
            aliases.add(new Alias(field, title));
        }
    }

    private enum Field {
        COMPANY_NAME,
        TARGET_ROLE,
        MAIN_RESPONSIBILITIES,
        QUALIFICATIONS,
        PREFERRED_QUALIFICATIONS,
        TECHNOLOGIES_TOOLS,
        CORE_COMPETENCIES,
        COMPANY_BUSINESS_INTRO
    }

    private record Alias(Field field, String title) {
    }

    private record Header(Field field, String inlineValue) {
    }
}
