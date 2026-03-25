package com.wildlifevn.backend.model;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "species")
public class SpeciesDocument {
    @Id
    private String id;

    @Field("scientific_name")
    private String scientificName;

    @Field("common_name_vi")
    private String vietnameseName;

    @Field("conservation_status")
    private String conservationStatus;

    @Field("description")
    private String shortDescription;

    @Field("image_url")
    private String heroImageUrl;

    @Field("media_assets")
    private List<SpeciesMedia> media = new ArrayList<>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getScientificName() {
        return scientificName;
    }

    public void setScientificName(String scientificName) {
        this.scientificName = scientificName;
    }

    public String getVietnameseName() {
        return vietnameseName;
    }

    public void setVietnameseName(String vietnameseName) {
        this.vietnameseName = vietnameseName;
    }

    public String getConservationStatus() {
        return conservationStatus;
    }

    public void setConservationStatus(String conservationStatus) {
        this.conservationStatus = conservationStatus;
    }

    public String getShortDescription() {
        return shortDescription;
    }

    public void setShortDescription(String shortDescription) {
        this.shortDescription = shortDescription;
    }

    public String getHeroImageUrl() {
        return heroImageUrl;
    }

    public void setHeroImageUrl(String heroImageUrl) {
        this.heroImageUrl = heroImageUrl;
    }

    public List<SpeciesMedia> getMedia() {
        return media;
    }

    public void setMedia(List<SpeciesMedia> media) {
        this.media = media;
    }
}
