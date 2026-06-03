package com.wildlifevn.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.wildlifevn.backend.client.AiServerClient;
import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.request.ClearSessionRequest;
import com.wildlifevn.backend.dto.request.ConfirmSpeciesRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ChatbotServiceTest {

    @Mock
    private AiServerClient aiServerClient;

    @InjectMocks
    private ChatbotService chatbotService;

    @Test
    void queryReturnsFallbackWhenAiServerIsUnavailable() {
        ChatQueryRequest request = new ChatQueryRequest();
        request.setSessionId("session-1");
        request.setQuestion("Xin chào");
        when(aiServerClient.query(request)).thenThrow(new IllegalStateException("connection refused"));

        ChatQueryResponse response = chatbotService.query(request);

        assertThat(response.status()).isEqualTo("AI_SERVER_ERROR");
        assertThat(response.message()).contains("AI server");
        assertThat(response.answer()).isNull();
        assertThat(response.candidates()).isEmpty();
    }

    @Test
    void queryDebugReturnsFallbackDebugPayload() {
        ChatQueryRequest request = new ChatQueryRequest();
        request.setSessionId("session-1");
        request.setQuestion("debug");
        when(aiServerClient.queryDebug(request)).thenThrow(new IllegalStateException("timeout"));

        Map<String, Object> response = chatbotService.queryDebug(request);

        assertThat(response).containsEntry("status", "AI_SERVER_ERROR");
        assertThat(response).containsKey("debug");
    }

    @Test
    void confirmSpeciesReturnsFallbackWhenAiServerIsUnavailable() {
        when(aiServerClient.confirmSpecies(any(ConfirmSpeciesRequest.class)))
                .thenThrow(new IllegalStateException("connection refused"));

        ChatQueryResponse response = chatbotService.confirmSpecies("session-1", "sp-1");

        assertThat(response.status()).isEqualTo("AI_SERVER_ERROR");
        assertThat(response.activeSpeciesId()).isNull();
    }

    @Test
    void clearSpeciesReturnsFallbackWhenAiServerIsUnavailable() {
        when(aiServerClient.clearSpecies(any(ClearSessionRequest.class)))
                .thenThrow(new IllegalStateException("connection refused"));

        ChatQueryResponse response = chatbotService.clearSpeciesContext("session-1");

        assertThat(response.status()).isEqualTo("AI_SERVER_ERROR");
        assertThat(response.candidates()).isEmpty();
    }

    @Test
    void ragHealthReturnsUnavailableWhenAiServerIsUnavailable() {
        when(aiServerClient.ragHealth(false)).thenThrow(new IllegalStateException("connection refused"));

        Map<String, Object> response = chatbotService.ragHealth(false);

        assertThat(response).containsEntry("status", "unavailable");
        assertThat(response).containsEntry("loaded", false);
    }
}
