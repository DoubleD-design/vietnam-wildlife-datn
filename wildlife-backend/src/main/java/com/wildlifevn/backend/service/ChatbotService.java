package com.wildlifevn.backend.service;

import com.wildlifevn.backend.dto.request.ChatQueryRequest;
import com.wildlifevn.backend.dto.response.ChatQueryResponse;
import com.wildlifevn.backend.dto.response.SpeciesCandidateResponse;
import com.wildlifevn.backend.model.SpeciesDocument;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class ChatbotService {
    private static final String OUT_OF_SCOPE_MESSAGE = "Mình chưa thể trả lời câu hỏi này vì nội dung vượt ngoài phạm vi dữ liệu hiện có của mình.";
    private static final String UNKNOWN_IMAGE_MESSAGE = "Xin lỗi, tôi chưa nhận diện được loài này trong cơ sở dữ liệu hiện tại. Vui lòng thử ảnh khác rõ hơn.";

    private final SpeciesService speciesService;
    private final Map<String, SessionState> sessions = new ConcurrentHashMap<>();

    public ChatbotService(SpeciesService speciesService) {
        this.speciesService = speciesService;
    }

    public ChatQueryResponse query(ChatQueryRequest request) {
        SessionState state = sessions.computeIfAbsent(request.getSessionId(), key -> new SessionState());

        boolean hasImage = request.getImageUrl() != null && !request.getImageUrl().isBlank();
        boolean hasQuestion = request.getQuestion() != null && !request.getQuestion().isBlank();

        if (!hasImage && !hasQuestion) {
            throw new IllegalArgumentException("Request must contain question or imageUrl");
        }

        if (hasImage) {
            return handleImageFlow(request, state, hasQuestion);
        }

        return handleTextOnlyFlow(request.getQuestion(), state);
    }

    public ChatQueryResponse confirmSpecies(String sessionId, String speciesId) {
        SessionState state = sessions.computeIfAbsent(sessionId, key -> new SessionState());

        SpeciesDocument species = speciesService.getSpeciesOrThrow(speciesId);
        state.currentSpeciesId = species.getId();
        state.currentSpeciesName = displayName(species);
        state.awaitingConfirmation = false;
        state.pendingCandidates = List.of();

        if (state.pendingQuestion != null && !state.pendingQuestion.isBlank()) {
            String answer = answerWithContext(state.pendingQuestion, species);
            state.pendingQuestion = null;
            return new ChatQueryResponse(
                    "ANSWERED",
                    "Đã xác nhận loài và trả lời câu hỏi của bạn.",
                    answer,
                    state.currentSpeciesId,
                    state.currentSpeciesName,
                    List.of());
        }

        return new ChatQueryResponse(
                "SPECIES_CONFIRMED",
                "Đã cập nhật loài đang trao đổi.",
                null,
                state.currentSpeciesId,
                state.currentSpeciesName,
                List.of());
    }

    public ChatQueryResponse clearSpeciesContext(String sessionId) {
        SessionState state = sessions.computeIfAbsent(sessionId, key -> new SessionState());
        state.currentSpeciesId = null;
        state.currentSpeciesName = null;
        state.pendingQuestion = null;
        state.awaitingConfirmation = false;
        state.pendingCandidates = List.of();

        return new ChatQueryResponse(
                "CLEARED",
                "Đã xóa ngữ cảnh loài đang chọn. Bạn có thể hỏi chung hoặc gửi ảnh mới.",
                null,
                null,
                null,
                List.of());
    }

    private ChatQueryResponse handleImageFlow(ChatQueryRequest request, SessionState state, boolean hasQuestion) {
        if (Boolean.TRUE.equals(request.getImageRejected())) {
            return new ChatQueryResponse("UNKNOWN_SPECIES", UNKNOWN_IMAGE_MESSAGE, null, state.currentSpeciesId,
                    state.currentSpeciesName, List.of());
        }

        List<SpeciesCandidateResponse> candidates = speciesService.topCandidatesFromCurrentData(6)
                .stream()
                .map(card -> new SpeciesCandidateResponse(card.id(), card.scientificName(), card.vietnameseName(),
                        card.heroImageUrl()))
                .toList();

        if (candidates.isEmpty()) {
            return new ChatQueryResponse("UNKNOWN_SPECIES", UNKNOWN_IMAGE_MESSAGE, null, state.currentSpeciesId,
                    state.currentSpeciesName, List.of());
        }

        state.awaitingConfirmation = true;
        state.pendingCandidates = new ArrayList<>(candidates);
        state.pendingQuestion = hasQuestion ? request.getQuestion() : null;

        String message = hasQuestion
                ? "Vui lòng chọn đúng loài trong danh sách, hệ thống sẽ tự động trả lời câu hỏi ngay sau khi bạn xác nhận."
                : "Vui lòng chọn loài phù hợp trong danh sách để tiếp tục.";

        return new ChatQueryResponse(
                "NEED_SPECIES_CONFIRM",
                message,
                null,
                state.currentSpeciesId,
                state.currentSpeciesName,
                candidates);
    }

    private ChatQueryResponse handleTextOnlyFlow(String question, SessionState state) {
        Optional<SpeciesDocument> mentionedSpecies = speciesService.findSpeciesMention(question);
        SpeciesDocument activeSpecies = null;

        if (mentionedSpecies.isPresent()) {
            activeSpecies = mentionedSpecies.get();
            state.currentSpeciesId = activeSpecies.getId();
            state.currentSpeciesName = displayName(activeSpecies);
        } else if (state.currentSpeciesId != null) {
            activeSpecies = speciesService.getSpeciesOrThrow(state.currentSpeciesId);
        }

        String answer = answerWithContext(question, activeSpecies);

        return new ChatQueryResponse(
                "ANSWERED",
                mentionedSpecies.isPresent() ? "Đã chuyển sang loài bạn vừa đề cập trong câu hỏi."
                        : "Đã xử lý câu hỏi.",
                answer,
                state.currentSpeciesId,
                state.currentSpeciesName,
                List.of());
    }

    private String answerWithContext(String question, SpeciesDocument species) {
        if (isOutOfScope(question)) {
            return OUT_OF_SCOPE_MESSAGE;
        }

        if (species != null && species.getShortDescription() != null && !species.getShortDescription().isBlank()) {
            return "Theo dữ liệu hiện có về loài " + displayName(species) + ": " + species.getShortDescription();
        }

        return OUT_OF_SCOPE_MESSAGE;
    }

    private boolean isOutOfScope(String question) {
        String q = question.toLowerCase(Locale.ROOT);
        return q.contains("bóng đá") || q.contains("bitcoin") || q.contains("chứng khoán") || q.contains("thời tiết");
    }

    private String displayName(SpeciesDocument species) {
        if (species.getVietnameseName() != null && !species.getVietnameseName().isBlank()) {
            return species.getVietnameseName();
        }
        return species.getScientificName();
    }

    private static class SessionState {
        private String currentSpeciesId;
        private String currentSpeciesName;
        private String pendingQuestion;
        private boolean awaitingConfirmation;
        private List<SpeciesCandidateResponse> pendingCandidates = List.of();
    }
}
