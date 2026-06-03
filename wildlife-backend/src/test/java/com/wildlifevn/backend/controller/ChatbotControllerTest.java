package com.wildlifevn.backend.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import com.wildlifevn.backend.service.ChatbotService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ChatbotController.class)
class ChatbotControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ChatbotService chatbotService;

    @Test
    void queryReturnsAssistantResponse() throws Exception {
        when(chatbotService.query(any(ChatQueryRequest.class)))
                .thenReturn(new ChatQueryResponse(
                        "OK",
                        "Đã xử lý",
                        "Câu trả lời từ AI",
                        "sp-1",
                        "Voọc chà vá chân đỏ",
                        List.of()));

        mockMvc.perform(post("/api/chatbot/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "sessionId", "session-1",
                                "question", "Loài này sống ở đâu?"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"))
                .andExpect(jsonPath("$.answer").value("Câu trả lời từ AI"))
                .andExpect(jsonPath("$.activeSpeciesId").value("sp-1"));

        verify(chatbotService).query(any(ChatQueryRequest.class));
    }

    @Test
    void queryRejectsMissingSessionId() throws Exception {
        mockMvc.perform(post("/api/chatbot/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "question", "Xin chào"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Invalid request payload"));
    }

    @Test
    void queryRejectsUnsupportedImagePayload() throws Exception {
        mockMvc.perform(post("/api/chatbot/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "sessionId", "session-1",
                                "imageUrl", "https://example.com/image.jpg"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Invalid request payload"));
    }

    @Test
    void confirmSpeciesReturnsResponse() throws Exception {
        when(chatbotService.confirmSpecies("session-1", "sp-1"))
                .thenReturn(new ChatQueryResponse("OK", "Đã xác nhận loài.", null, "sp-1", "Voọc", List.of()));

        mockMvc.perform(post("/api/chatbot/confirm-species")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "sessionId", "session-1",
                                "speciesId", "sp-1"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"))
                .andExpect(jsonPath("$.activeSpeciesId").value("sp-1"));

        verify(chatbotService).confirmSpecies("session-1", "sp-1");
    }

    @Test
    void clearSpeciesReturnsResponse() throws Exception {
        when(chatbotService.clearSpeciesContext("session-1"))
                .thenReturn(new ChatQueryResponse("OK", "Đã xóa ngữ cảnh loài.", null, null, null, List.of()));

        mockMvc.perform(post("/api/chatbot/clear-species")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("sessionId", "session-1"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"))
                .andExpect(jsonPath("$.message").value("Đã xóa ngữ cảnh loài."));
    }

    @Test
    void ragHealthReturnsRuntimeStatus() throws Exception {
        when(chatbotService.ragHealth(true))
                .thenReturn(Map.of("status", "ok", "loaded", true, "chunksMetadataCount", 5000));

        mockMvc.perform(get("/api/chatbot/rag-health").param("load", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.loaded").value(true))
                .andExpect(jsonPath("$.chunksMetadataCount").value(5000));

        verify(chatbotService).ragHealth(true);
    }
}
