import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchSpeciesScientificProfile,
  prefetchImage,
} from "../services/speciesService";
import "../App.css";

function readValue(source, keys, fallback = null) {
  for (const key of keys) {
    if (source?.[key] !== undefined && source[key] !== null) {
      return source[key];
    }
  }
  return fallback;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function formatList(value, emptyText = "Chưa có dữ liệu") {
  const arr = toArray(value).filter(Boolean);
  return arr.length > 0 ? arr.join(", ") : emptyText;
}

function SpeciesDetailPage() {
  const { speciesId } = useParams();
  const [profile, setProfile] = useState(null);
  const [selectedMediaIndex, setSelectedMediaIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadSpeciesDetail() {
      setIsLoading(true);
      setError("");

      try {
        const profileData = await fetchSpeciesScientificProfile(speciesId);

        if (!isMounted) {
          return;
        }

        setProfile(profileData || null);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        setError(
          loadError?.response?.data?.message ||
            "Không tải được hồ sơ loài từ backend. Kiểm tra API server và speciesId.",
        );
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadSpeciesDetail();
    return () => {
      isMounted = false;
    };
  }, [speciesId]);

  const taxonomy = useMemo(
    () => toObject(readValue(profile, ["taxonomy"], {})),
    [profile],
  );

  const distribution = useMemo(
    () => toObject(readValue(profile, ["distribution"], {})),
    [profile],
  );

  const ecology = useMemo(
    () => toObject(readValue(profile, ["ecology"], {})),
    [profile],
  );

  const conservation = useMemo(
    () => toObject(readValue(profile, ["conservation"], {})),
    [profile],
  );

  const mediaAssets = useMemo(() => {
    return toArray(readValue(profile, ["mediaAssets", "media_assets"], []));
  }, [profile]);

  const heroImage =
    readValue(profile, ["imageUrl", "image_url"]) ||
    readValue(mediaAssets[0], ["blob_url", "url"]) ||
    "";

  const galleryImages = useMemo(() => {
    const items = mediaAssets
      .map((asset, index) => {
        const url = readValue(asset, ["blob_url", "url"], "");
        if (!url) {
          return null;
        }
        return {
          key: `${url}-${index}`,
          url,
          asset,
        };
      })
      .filter(Boolean);

    if (heroImage && !items.some((item) => item.url === heroImage)) {
      items.unshift({
        key: `${heroImage}-hero`,
        url: heroImage,
        asset: {
          type: "image",
          blob_url: heroImage,
          is_hero: true,
        },
      });
    }

    return items;
  }, [mediaAssets, heroImage]);

  useEffect(() => {
    setSelectedMediaIndex(0);
  }, [speciesId, galleryImages.length]);

  useEffect(() => {
    if (galleryImages.length === 0) {
      return;
    }

    const warmupUrls = galleryImages
      .slice(0, 4)
      .map((item) => item.url)
      .filter(Boolean);
    if (typeof window !== "undefined" && "requestIdleCallback" in window) {
      window.requestIdleCallback(() => {
        warmupUrls.forEach((url) => prefetchImage(url));
      });
    } else {
      setTimeout(() => {
        warmupUrls.forEach((url) => prefetchImage(url));
      }, 120);
    }
  }, [galleryImages]);

  const selectedMedia =
    galleryImages[selectedMediaIndex] || galleryImages[0] || null;

  useEffect(() => {
    if (!selectedMedia) {
      return;
    }

    prefetchImage(selectedMedia.url);

    const next = galleryImages[selectedMediaIndex + 1];
    const prev = galleryImages[selectedMediaIndex - 1];
    if (next?.url) {
      prefetchImage(next.url);
    }
    if (prev?.url) {
      prefetchImage(prev.url);
    }
  }, [selectedMedia, selectedMediaIndex, galleryImages]);

  const scientificName = readValue(
    profile,
    ["scientificName", "scientific_name"],
    "",
  );
  const vietnameseName = readValue(
    profile,
    ["commonNameVi", "common_name_vi"],
    "",
  );
  const commonNameEn = readValue(
    profile,
    ["commonNameEn", "common_name_en"],
    "",
  );
  const canonicalId = readValue(profile, ["canonicalId", "canonical_id"], "");
  const authority = readValue(profile, ["authority"], "unknown");
  const rank = readValue(profile, ["rank"], "species");
  const group = readValue(profile, ["group"], "");
  const description = readValue(profile, ["description"], "");
  const behavior = readValue(profile, ["behavior"], "");

  const iucnCategory = readValue(
    conservation,
    ["iucnCategory", "iucn_category"],
    "unknown",
  );
  const iucnYear = readValue(
    conservation,
    ["iucnYear", "iucn_year"],
    "unknown",
  );
  const populationTrend = readValue(
    conservation,
    ["populationTrend", "population_trend"],
    "unknown",
  );
  const citesAppendix = readValue(
    conservation,
    ["citesAppendix", "cites_appendix"],
    "unknown",
  );
  const vnRedCategory = readValue(
    conservation,
    ["vietnamRedDataCategory", "vietnam_red_data_category"],
    "unknown",
  );
  const vnRedYear = readValue(
    conservation,
    ["vietnamRedDataYear", "vietnam_red_data_year"],
    "unknown",
  );
  const majorThreats = toArray(
    readValue(conservation, ["majorThreats", "major_threats"], []),
  );

  const habitatTags = toArray(
    readValue(ecology, ["habitatTags", "habitat_tags"], []),
  );
  const diet = toArray(readValue(ecology, ["diet"], []));
  const activityPattern = readValue(
    ecology,
    ["activityPattern", "activity_pattern"],
    "unknown",
  );

  const countries = toArray(readValue(distribution, ["countries"], []));
  const regionsVi = toArray(
    readValue(distribution, ["regionsVi", "regions_vi"], []),
  );
  const provinces = toArray(readValue(distribution, ["provinces"], []));
  const protectedAreas = toArray(
    readValue(distribution, ["protectedAreas", "protected_areas"], []),
  );

  const searchKeywords = toArray(
    readValue(profile, ["searchKeywords", "search_keywords"], []),
  );

  if (isLoading) {
    return (
      <main className="detail-page-wrap">
        <section className="detail-page not-found">
          <h1>Đang tải hồ sơ loài...</h1>
          <p>Hệ thống đang lấy dữ liệu từ MongoDB qua backend API.</p>
        </section>
      </main>
    );
  }

  if (error || !profile) {
    return (
      <main className="detail-page-wrap">
        <section className="detail-page not-found">
          <h1>Không tải được dữ liệu loài</h1>
          <p>{error || "Loài không tồn tại trong cơ sở dữ liệu."}</p>
          <Link className="primary-btn" to="/">
            Quay về trang chủ
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="detail-page-wrap">
      <section className="detail-page">
        <Link className="detail-back-link" to="/">
          ← Quay lại thư viện
        </Link>

        <div className="detail-hero">
          <div className="detail-gallery-column">
            <img
              className="detail-main-image"
              src={selectedMedia?.url || heroImage}
              alt={vietnameseName || scientificName}
              loading="eager"
              decoding="async"
              fetchPriority="high"
            />

            {galleryImages.length > 0 ? (
              <div
                className="detail-thumbnail-strip"
                role="list"
                aria-label="Danh sách ảnh loài"
                style={{
                  gridTemplateColumns: `repeat(${galleryImages.length}, minmax(0, 1fr))`,
                }}
              >
                {galleryImages.map((image, index) => (
                  <button
                    key={image.key}
                    type="button"
                    className={`detail-thumb ${index === selectedMediaIndex ? "active" : ""}`}
                    onClick={() => setSelectedMediaIndex(index)}
                    onMouseEnter={() => prefetchImage(image.url)}
                    aria-label={`Xem ảnh ${index + 1}`}
                    aria-pressed={index === selectedMediaIndex}
                  >
                    <img
                      className="detail-thumb-image"
                      src={image.url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      fetchPriority="low"
                    />
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="detail-content">
            <p className="detail-tag">Hồ sơ loài</p>
            <h1>{vietnameseName || "Chưa có tên tiếng Việt"}</h1>
            <p className="detail-sci-name">{scientificName}</p>
            {commonNameEn ? (
              <p className="detail-summary">Tên tiếng Anh: {commonNameEn}</p>
            ) : null}

            <ul className="detail-facts-list">
              {/* <li>
                <strong>ID MongoDB:</strong>{" "}
                {readValue(profile, ["id", "_id"], speciesId)}
              </li> */}
              <li>
                <strong>Canonical ID:</strong> {canonicalId || "unknown"}
              </li>
              <li>
                <strong>Authority:</strong> {authority}
              </li>
              <li>
                <strong>Rank:</strong> {rank}
              </li>
              <li>
                <strong>Group:</strong> {group || "unknown"}
              </li>
            </ul>

            <Link
              to={`/qa?speciesId=${encodeURIComponent(speciesId)}&speciesName=${encodeURIComponent(vietnameseName || scientificName || "")}`}
              className="detail-chatbot-btn"
            >
              Hỏi Chatbot về loài này
            </Link>
          </div>
        </div>

        <section className="detail-section-grid">
          <article className="detail-section-card">
            <h3>Phân loại học (Taxonomy)</h3>
            <div className="kv-grid">
              <p>
                <strong>Kingdom:</strong>{" "}
                {readValue(taxonomy, ["kingdom"], "unknown")}
              </p>
              <p>
                <strong>Phylum:</strong>{" "}
                {readValue(taxonomy, ["phylum"], "unknown")}
              </p>
              <p>
                <strong>Class:</strong>{" "}
                {readValue(taxonomy, ["class"], "unknown")}
              </p>
              <p>
                <strong>Order:</strong>{" "}
                {readValue(taxonomy, ["order"], "unknown")}
              </p>
              <p>
                <strong>Family:</strong>{" "}
                {readValue(taxonomy, ["family"], "unknown")}
              </p>
              <p>
                <strong>Genus:</strong>{" "}
                {readValue(taxonomy, ["genus"], "unknown")}
              </p>
            </div>
          </article>

          <article className="detail-section-card">
            <h3>Bảo tồn</h3>
            <div className="kv-grid">
              <p>
                <strong>IUCN:</strong> {iucnCategory}
              </p>
              <p>
                <strong>IUCN Year:</strong> {iucnYear}
              </p>
              <p>
                <strong>Population Trend:</strong> {populationTrend}
              </p>
              <p>
                <strong>CITES Appendix:</strong> {citesAppendix}
              </p>
              <p>
                <strong>Việt Nam Red Data:</strong> {vnRedCategory}
              </p>
              <p>
                <strong>VN Red Data Year:</strong> {vnRedYear}
              </p>
            </div>
            <p>
              <strong>Mối đe doạ chính:</strong> {formatList(majorThreats)}
            </p>
          </article>

          <article className="detail-section-card">
            <h3>Phân bố</h3>
            <p>
              <strong>Countries:</strong> {formatList(countries)}
            </p>
            <p>
              <strong>Regions (VN):</strong> {formatList(regionsVi)}
            </p>
            <p>
              <strong>Provinces:</strong> {formatList(provinces)}
            </p>
            <p>
              <strong>Protected Areas:</strong> {formatList(protectedAreas)}
            </p>
          </article>

          <article className="detail-section-card">
            <h3>Sinh thái & Tập tính</h3>
            <p>
              <strong>Habitat Tags:</strong> {formatList(habitatTags)}
            </p>
            <p>
              <strong>Activity Pattern:</strong> {activityPattern}
            </p>
            <p>
              <strong>Diet:</strong> {formatList(diet)}
            </p>
            <p>
              <strong>Behavior:</strong> {behavior || "Chưa có dữ liệu"}
            </p>
          </article>
        </section>

        <section className="detail-section-card detail-description-block">
          <h3>Mô tả chi tiết</h3>
          <p>{description || "Chưa có mô tả."}</p>
        </section>

        <section className="detail-section-card">
          <h3>Từ khóa tìm kiếm</h3>
          <div className="tag-cloud">
            {searchKeywords.length === 0 ? (
              <p>Chưa có dữ liệu từ khóa.</p>
            ) : (
              searchKeywords.map((tag) => (
                <span key={tag} className="keyword-chip">
                  {tag}
                </span>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

export default SpeciesDetailPage;
