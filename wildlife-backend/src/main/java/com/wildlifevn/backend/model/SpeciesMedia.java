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

    @Field("thumbnail_url")
    private String thumbnailUrl;

    @Field("thumbnail_width")
    private Integer thumbnailWidth;

    @Field("thumbnail_height")
    private Integer thumbnailHeight;

    @Field("thumbnail_format")
    private String thumbnailFormat;

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

    public String getThumbnailUrl() {
        return thumbnailUrl;
    }

    public void setThumbnailUrl(String thumbnailUrl) {
        this.thumbnailUrl = thumbnailUrl;
    }

    public Integer getThumbnailWidth() {
        return thumbnailWidth;
    }

    public void setThumbnailWidth(Integer thumbnailWidth) {
        this.thumbnailWidth = thumbnailWidth;
    }

    public Integer getThumbnailHeight() {
        return thumbnailHeight;
    }

    public void setThumbnailHeight(Integer thumbnailHeight) {
        this.thumbnailHeight = thumbnailHeight;
    }

    public String getThumbnailFormat() {
        return thumbnailFormat;
    }

    public void setThumbnailFormat(String thumbnailFormat) {
        this.thumbnailFormat = thumbnailFormat;
    }
}
