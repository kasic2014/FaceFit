package com.facefit.backend.interview.api;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public final class InterviewSessionPatchRequest {

    public static final Set<String> ALLOWED_FIELDS = Set.of(
            "resumeDocumentId",
            "coverLetterDocumentId",
            "jobPostingId",
            "persona",
            "difficulty"
    );

    private final Map<String, JsonNode> fields;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public InterviewSessionPatchRequest(Map<String, JsonNode> fields) {
        this.fields = fields == null ? Map.of() : Map.copyOf(new LinkedHashMap<>(fields));
    }

    public boolean isEmpty() {
        return fields.isEmpty();
    }

    public Set<String> fieldNames() {
        return fields.keySet();
    }

    public boolean contains(String name) {
        return fields.containsKey(name);
    }

    public JsonNode value(String name) {
        return fields.get(name);
    }
}
