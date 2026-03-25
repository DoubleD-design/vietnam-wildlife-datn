package com.wildlifevn.backend.dto.request;

import jakarta.validation.constraints.NotBlank;

public class ClearSessionRequest {
    @NotBlank
    private String sessionId;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }
}
