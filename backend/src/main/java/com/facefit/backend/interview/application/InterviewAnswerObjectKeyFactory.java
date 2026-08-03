package com.facefit.backend.interview.application;

import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class InterviewAnswerObjectKeyFactory {

    public String create(
            UUID sessionId,
            UUID turnId,
            UUID answerId,
            String extension
    ) {
        return "sessions/"
                + sessionId
                + "/turns/"
                + turnId
                + "/"
                + answerId
                + "."
                + extension;
    }
}
