package com.wildlifevn.backend.service;

import com.wildlifevn.backend.client.AiServerClient;
import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.request.ClearSessionRequest;
import com.wildlifevn.backend.dto.request.ConfirmSpeciesRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ChatbotService {
    private static final String AI_SERVER_UNAVAILABLE = "AI server hiện chưa phản hồi. Vui lòng thử lại sau ít phút.";

    private final AiServerClient aiServerClient;

    public ChatbotService(AiServerClient aiServerClient) {
        this.aiServerClient = aiServerClient;
    }

    public ChatQueryResponse query(ChatQueryRequest request) {
        try {
            return aiServerClient.query(request);
        } catch (IllegalStateException ex) {
            return fallback("AI_SERVER_ERROR", AI_SERVER_UNAVAILABLE);
        }
    }

    public ChatQueryResponse confirmSpecies(String sessionId, String speciesId) {
        ConfirmSpeciesRequest request = new ConfirmSpeciesRequest();
        request.setSessionId(sessionId);
        request.setSpeciesId(speciesId);

        try {
            return aiServerClient.confirmSpecies(request);
        } catch (IllegalStateException ex) {
            return fallback("AI_SERVER_ERROR", AI_SERVER_UNAVAILABLE);
        }
    }

    public ChatQueryResponse clearSpeciesContext(String sessionId) {
        ClearSessionRequest request = new ClearSessionRequest();
        request.setSessionId(sessionId);

        try {
            return aiServerClient.clearSpecies(request);
        } catch (IllegalStateException ex) {
            return fallback("AI_SERVER_ERROR", AI_SERVER_UNAVAILABLE);
        }
    }

    private ChatQueryResponse fallback(String status, String message) {
        return new ChatQueryResponse(
                status,
                message,
                null,
                null,
                null,
                List.of());
    }
}
