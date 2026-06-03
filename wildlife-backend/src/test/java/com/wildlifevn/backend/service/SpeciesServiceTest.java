package com.wildlifevn.backend.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.wildlifevn.backend.dto.response.SpeciesDetailResponse;
import com.wildlifevn.backend.dto.response.SpeciesScientificProfileResponse;
import com.wildlifevn.backend.model.SpeciesDocument;
import com.wildlifevn.backend.model.SpeciesMedia;
import com.wildlifevn.backend.repository.SpeciesRepository;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@ExtendWith(MockitoExtension.class)
class SpeciesServiceTest {

    @Mock
    private SpeciesRepository speciesRepository;

    @Mock
    private MongoTemplate mongoTemplate;

    @InjectMocks
    private SpeciesService speciesService;

    @Test
    void getSpeciesDetailMapsFallbackImageMediaAndConservation() {
        SpeciesDocument species = sampleSpeciesDocument();
        when(speciesRepository.findById("sp-1")).thenReturn(Optional.of(species));

        SpeciesDetailResponse response = speciesService.getSpeciesDetail("sp-1");

        assertThat(response.id()).isEqualTo("sp-1");
        assertThat(response.conservationStatus()).isEqualTo("EN");
        assertThat(response.shortDescription()).isEqualTo("Mô tả ngắn");
        assertThat(response.heroImageUrl()).isEqualTo("https://cdn.example/medium.jpg");
        assertThat(response.mediaUrls()).containsExactly("https://cdn.example/medium.jpg");
    }

    @Test
    void getSpeciesDetailThrowsWhenSpeciesDoesNotExist() {
        when(speciesRepository.findById("not-found")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> speciesService.getSpeciesDetail("not-found"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Species not found: not-found");
    }

    @Test
    void listSpeciesCapsUnsafePageAndSizeAndMapsDocumentCards() {
        Document speciesDoc = new Document("_id", "sp-1")
                .append("scientific_name", "Pygathrix nemaeus")
                .append("common_name_vi", "Voọc chà vá chân đỏ")
                .append("group", "Mammalia")
                .append("conservation", Map.of("iucn_category", "VU"))
                .append("distribution", Map.of("regions_vi", List.of("Trung Bộ")))
                .append("media_assets", List.of(Map.of(
                        "is_hero", true,
                        "medium_url", "https://cdn.example/medium.jpg",
                        "thumbnail_url", "https://cdn.example/thumb.jpg")));
        when(mongoTemplate.count(any(Query.class), eq(SpeciesDocument.class))).thenReturn(1L);
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("species")))
                .thenReturn(List.of(speciesDoc));

        Page<?> page = speciesService.listSpecies("vooc", "thu", "VU", -5, 999);

        assertThat(page.getNumber()).isZero();
        assertThat(page.getSize()).isEqualTo(100);
        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getContent().getFirst())
                .extracting("id", "conservationStatus", "heroImageUrl", "thumbnailUrl", "region")
                .containsExactly(
                        "sp-1",
                        "VU",
                        "https://cdn.example/medium.jpg",
                        "https://cdn.example/thumb.jpg",
                        "Trung Bộ");
    }

    @Test
    void scientificProfileMapsMongoDocumentFields() {
        ObjectId id = new ObjectId();
        Document document = new Document("_id", id)
                .append("canonical_id", "pygathrix-nemaeus")
                .append("scientific_name", "Pygathrix nemaeus")
                .append("common_name_vi", "Voọc chà vá chân đỏ")
                .append("common_name_en", "Red-shanked douc")
                .append("rank", "species")
                .append("group", "Mammalia")
                .append("taxonomy", Map.of("family", "Cercopithecidae"))
                .append("media_assets", List.of(Map.of("blob_url", "https://cdn.example/hero.jpg")))
                .append("distribution", Map.of("regions_vi", List.of("Trung Bộ")))
                .append("conservation", Map.of("iucn_category", "EN"))
                .append("search_keywords", List.of("voọc", "douc"));
        when(mongoTemplate.findOne(any(Query.class), eq(Document.class), eq("species")))
                .thenReturn(document);

        SpeciesScientificProfileResponse response = speciesService.getSpeciesScientificProfile(id.toHexString());

        assertThat(response.id()).isEqualTo(id.toHexString());
        assertThat(response.commonNameVi()).isEqualTo("Voọc chà vá chân đỏ");
        assertThat(response.taxonomy()).containsEntry("family", "Cercopithecidae");
        assertThat(response.mediaAssets()).hasSize(1);
        assertThat(response.searchKeywords()).containsExactly("voọc", "douc");
    }

    private SpeciesDocument sampleSpeciesDocument() {
        SpeciesMedia media = new SpeciesMedia();
        media.setHero(true);
        media.setMediumUrl("https://cdn.example/medium.jpg");
        media.setBlobUrl("https://cdn.example/blob.jpg");
        media.setThumbnailUrl("https://cdn.example/thumb.jpg");

        SpeciesDocument species = new SpeciesDocument();
        species.setId("sp-1");
        species.setScientificName("Pygathrix nemaeus");
        species.setVietnameseName("Voọc chà vá chân đỏ");
        species.setShortDescription("Mô tả ngắn");
        species.setGroup("Mammalia");
        species.setConservation(Map.of("iucn_category", "EN"));
        species.setDistribution(Map.of("regions_vi", List.of("Trung Bộ")));
        species.setMedia(List.of(media));
        return species;
    }
}
