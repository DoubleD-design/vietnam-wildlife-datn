package com.wildlifevn.backend.dto.request;

import jakarta.validation.constraints.NotBlank;

public class ConfirmSpeciesRequest {
    @NotBlank
    private String sessionId;

    @NotBlank
    private String speciesId;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getSpeciesId() {
        return speciesId;
    }

    public void setSpeciesId(String speciesId) {
        this.speciesId = speciesId;
    }
}
