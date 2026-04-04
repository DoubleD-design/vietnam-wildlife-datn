package com.wildlifevn.backend.model;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
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

    @Field("group")
    private String group;

    @Field("distribution")
    private Map<String, Object> distribution;

    @Field("conservation")
    private Map<String, Object> conservation;

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

    public String getGroup() {
        return group;
    }

    public void setGroup(String group) {
        this.group = group;
    }

    public Map<String, Object> getDistribution() {
        return distribution;
    }

    public void setDistribution(Map<String, Object> distribution) {
        this.distribution = distribution;
    }

    public Map<String, Object> getConservation() {
        return conservation;
    }

    public void setConservation(Map<String, Object> conservation) {
        this.conservation = conservation;
    }

    public List<SpeciesMedia> getMedia() {
        return media;
    }

    public void setMedia(List<SpeciesMedia> media) {
        this.media = media;
    }
}
