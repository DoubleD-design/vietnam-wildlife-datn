package com.wildlifevn.backend.model;

import org.springframework.data.mongodb.core.mapping.Field;

public class SpeciesMedia {
    private String url;
    private String type;
    private String source;

    @Field("is_hero")
    private Boolean hero;

    @Field("blob_url")
    private String blobUrl;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public Boolean getHero() {
        return hero;
    }

    public void setHero(Boolean hero) {
        this.hero = hero;
    }

    public String getBlobUrl() {
        return blobUrl;
    }

    public void setBlobUrl(String blobUrl) {
        this.blobUrl = blobUrl;
    }
}
