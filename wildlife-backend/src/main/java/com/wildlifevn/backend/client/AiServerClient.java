package com.wildlifevn.backend.client;

import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.request.ClearSessionRequest;
import com.wildlifevn.backend.dto.request.ConfirmSpeciesRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

@Component
public class AiServerClient {

    private final RestTemplate restTemplate;
    private final String aiBaseUrl;

    public AiServerClient(
            @Value("${ai.server.base-url:http://localhost:8001}") String aiBaseUrl) {
        this.restTemplate = new RestTemplate();
        this.aiBaseUrl = aiBaseUrl;
    }

    public ChatQueryResponse query(ChatQueryRequest request) {
        return post("/api/chatbot/query", request);
    }

    public ChatQueryResponse confirmSpecies(ConfirmSpeciesRequest request) {
        return post("/api/chatbot/confirm-species", request);
    }

    public ChatQueryResponse clearSpecies(ClearSessionRequest request) {
        return post("/api/chatbot/clear-species", request);
    }

    private <T> ChatQueryResponse post(String path, T body) {
        try {
            ResponseEntity<ChatQueryResponse> response = restTemplate.postForEntity(
                    aiBaseUrl + path,
                    body,
                    ChatQueryResponse.class);
            ChatQueryResponse payload = response.getBody();
            if (payload == null) {
                throw new IllegalStateException("AI server returned empty response");
            }
            return payload;
        } catch (RestClientException ex) {
            throw new IllegalStateException("Cannot call AI server: " + ex.getMessage(), ex);
        }
    }
}
