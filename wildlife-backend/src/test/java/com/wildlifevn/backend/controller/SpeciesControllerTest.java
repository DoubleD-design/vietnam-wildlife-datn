package com.wildlifevn.backend.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.wildlifevn.backend.dto.response.SpeciesCardResponse;
import com.wildlifevn.backend.dto.response.SpeciesDetailResponse;
import com.wildlifevn.backend.dto.response.SpeciesScientificProfileResponse;
import com.wildlifevn.backend.service.SpeciesService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(SpeciesController.class)
class SpeciesControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private SpeciesService speciesService;

    @Test
    void listSpeciesReturnsPagedContract() throws Exception {
        SpeciesCardResponse card = new SpeciesCardResponse(
                "sp-1",
                "Pygathrix nemaeus",
                "Voọc chà vá chân đỏ",
                "EN",
                "https://cdn.example/hero.jpg",
                "https://cdn.example/thumb.jpg",
                "Mammalia",
                "Trung Bộ");
        when(speciesService.listSpecies("vooc", "thu", "EN", 0, 12))
                .thenReturn(new PageImpl<>(List.of(card), PageRequest.of(0, 12), 1));

        mockMvc.perform(get("/api/species")
                        .param("keyword", "vooc")
                        .param("sectorSlug", "thu")
                        .param("conservationStatus", "EN")
                        .param("page", "0")
                        .param("size", "12"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id").value("sp-1"))
                .andExpect(jsonPath("$.content[0].conservationStatus").value("EN"))
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(12))
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.totalPages").value(1));

        verify(speciesService).listSpecies("vooc", "thu", "EN", 0, 12);
    }

    @Test
    void getSpeciesSummaryReturnsDetailPayload() throws Exception {
        when(speciesService.getSpeciesDetail("sp-1"))
                .thenReturn(new SpeciesDetailResponse(
                        "sp-1",
                        "Pygathrix nemaeus",
                        "Voọc chà vá chân đỏ",
                        "EN",
                        "Mô tả ngắn",
                        "https://cdn.example/hero.jpg",
                        List.of("https://cdn.example/hero.jpg")));

        mockMvc.perform(get("/api/species/sp-1/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("sp-1"))
                .andExpect(jsonPath("$.vietnameseName").value("Voọc chà vá chân đỏ"))
                .andExpect(jsonPath("$.mediaUrls[0]").value("https://cdn.example/hero.jpg"));
    }

    @Test
    void getScientificProfileReturnsProfilePayload() throws Exception {
        when(speciesService.getSpeciesScientificProfile("sp-1"))
                .thenReturn(new SpeciesScientificProfileResponse(
                        "sp-1",
                        "pygathrix-nemaeus",
                        "Pygathrix nemaeus",
                        "Linnaeus",
                        "species",
                        "Voọc chà vá chân đỏ",
                        "Red-shanked douc",
                        "Mammalia",
                        Map.of("family", "Cercopithecidae"),
                        "https://cdn.example/hero.jpg",
                        List.of(Map.of("blob_url", "https://cdn.example/hero.jpg")),
                        "Mô tả",
                        Map.of("regions_vi", List.of("Trung Bộ")),
                        "Tập tính",
                        Map.of("diet", List.of("lá cây")),
                        Map.of("iucn_category", "EN"),
                        Map.of(),
                        Map.of(),
                        List.of("voọc")));

        mockMvc.perform(get("/api/species/sp-1/scientific-profile"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("sp-1"))
                .andExpect(jsonPath("$.commonNameVi").value("Voọc chà vá chân đỏ"))
                .andExpect(jsonPath("$.taxonomy.family").value("Cercopithecidae"));
    }

    @Test
    void getSpeciesMediaReturnsMediaPayload() throws Exception {
        when(speciesService.getSpeciesDetail("sp-1"))
                .thenReturn(new SpeciesDetailResponse(
                        "sp-1",
                        "Pygathrix nemaeus",
                        "Voọc chà vá chân đỏ",
                        "EN",
                        "Mô tả ngắn",
                        "https://cdn.example/hero.jpg",
                        List.of("https://cdn.example/hero.jpg", "https://cdn.example/second.jpg")));

        mockMvc.perform(get("/api/species/sp-1/media"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mediaUrls.length()").value(2));
    }

    @Test
    void notFoundSpeciesReturnsBadRequestMessage() throws Exception {
        when(speciesService.getSpeciesDetail(eq("not-found")))
                .thenThrow(new IllegalArgumentException("Species not found: not-found"));

        mockMvc.perform(get("/api/species/not-found/summary"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Species not found: not-found"));
    }
}
