package com.wildlifevn.backend.dto.request;

import jakarta.validation.constraints.NotBlank;

public class ChatQueryRequest {
    @NotBlank
    private String sessionId;
    private String question;
    private String imageUrl;
    private Boolean imageRejected;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getQuestion() {
        return question;
    }

    public void setQuestion(String question) {
        this.question = question;
    }

    public String getImageUrl() {
        return imageUrl;
    }

    public void setImageUrl(String imageUrl) {
        this.imageUrl = imageUrl;
    }

    public Boolean getImageRejected() {
        return imageRejected;
    }

    public void setImageRejected(Boolean imageRejected) {
        this.imageRejected = imageRejected;
    }
}
