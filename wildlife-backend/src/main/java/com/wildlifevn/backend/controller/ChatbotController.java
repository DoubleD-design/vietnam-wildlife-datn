package com.wildlifevn.backend.controller;

import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.request.ClearSessionRequest;
import com.wildlifevn.backend.dto.request.ConfirmSpeciesRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import com.wildlifevn.backend.service.ChatbotService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/chatbot")
@Tag(name = "Chatbot", description = "Chatbot APIs with species confirmation flow")
public class ChatbotController {

    private final ChatbotService chatbotService;

    public ChatbotController(ChatbotService chatbotService) {
        this.chatbotService = chatbotService;
    }

    @PostMapping("/query")
    @Operation(summary = "Send question/image", description = "Handle text-only, image-only, and image+question flow")
    public ResponseEntity<ChatQueryResponse> query(@Valid @RequestBody ChatQueryRequest request) {
        return ResponseEntity.ok(chatbotService.query(request));
    }

    @PostMapping("/confirm-species")
    @Operation(summary = "Confirm species", description = "Confirm species from candidate cards and optionally auto-answer pending question")
    public ResponseEntity<ChatQueryResponse> confirmSpecies(@Valid @RequestBody ConfirmSpeciesRequest request) {
        return ResponseEntity.ok(chatbotService.confirmSpecies(request.getSessionId(), request.getSpeciesId()));
    }

    @PostMapping("/clear-species")
    @Operation(summary = "Clear species context", description = "Clear current species from session without resetting full session")
    public ResponseEntity<ChatQueryResponse> clearSpecies(@Valid @RequestBody ClearSessionRequest request) {
        return ResponseEntity.ok(chatbotService.clearSpeciesContext(request.getSessionId()));
    }
}
