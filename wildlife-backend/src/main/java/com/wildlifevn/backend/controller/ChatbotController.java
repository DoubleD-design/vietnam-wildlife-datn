package com.wildlifevn.backend.controller;

import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.request.ClearSessionRequest;
import com.wildlifevn.backend.dto.request.ConfirmSpeciesRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import com.wildlifevn.backend.service.ChatbotService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/chatbot")
@Tag(name = "Chatbot", description = "Chatbot APIs with species confirmation flow")
public class ChatbotController {

    private static final Logger logger = LoggerFactory.getLogger(ChatbotController.class);

    private final ChatbotService chatbotService;

    public ChatbotController(ChatbotService chatbotService) {
        this.chatbotService = chatbotService;
    }

    @PostMapping("/query")
    @Operation(summary = "Send question/image", description = "Handle text-only, image-only, and image+question flow")
    public ResponseEntity<ChatQueryResponse> query(@Valid @RequestBody ChatQueryRequest request) {
        ChatQueryResponse result = chatbotService.query(request);
        logger.info(
                "[ChatbotAPI] POST /api/chatbot/query success sessionId={} status={}",
                request.getSessionId(),
                result.status());
        return ResponseEntity.ok(result);
    }

    @PostMapping("/confirm-species")
    @Operation(summary = "Confirm species", description = "Confirm species from candidate cards and optionally auto-answer pending question")
    public ResponseEntity<ChatQueryResponse> confirmSpecies(@Valid @RequestBody ConfirmSpeciesRequest request) {
        ChatQueryResponse result = chatbotService.confirmSpecies(request.getSessionId(), request.getSpeciesId());
        logger.info(
                "[ChatbotAPI] POST /api/chatbot/confirm-species success sessionId={} speciesId={} status={}",
                request.getSessionId(),
                request.getSpeciesId(),
                result.status());
        return ResponseEntity.ok(result);
    }

    @PostMapping("/clear-species")
    @Operation(summary = "Clear species context", description = "Clear current species from session without resetting full session")
    public ResponseEntity<ChatQueryResponse> clearSpecies(@Valid @RequestBody ClearSessionRequest request) {
        ChatQueryResponse result = chatbotService.clearSpeciesContext(request.getSessionId());
        logger.info(
                "[ChatbotAPI] POST /api/chatbot/clear-species success sessionId={} status={}",
                request.getSessionId(),
                result.status());
        return ResponseEntity.ok(result);
    }
}
