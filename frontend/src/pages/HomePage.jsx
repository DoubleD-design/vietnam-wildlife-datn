import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import redBirdImage from "../assets/red_bird.jpg";
import {
  fetchSpeciesList,
  fetchSpeciesSummary,
  prefetchImage,
} from "../services/speciesService";
import "../App.css";

const STATUS_LABELS = {
  all: "Tất cả mức bảo tồn",
  DD: "DD - Thiếu dữ liệu",
  LC: "LC - Ít quan tâm",
  NT: "NT - Gần đe dọa",
  VU: "VU - Sẽ nguy cấp",
  EN: "EN - Nguy cấp",
  CR: "CR - Cực kỳ nguy cấp",
};

const SPECIES_TYPE_LABELS = {
  all: "Tất cả nhóm loài",
  bird: "Chim",
  reptile: "Bò sát (thằn lằn, rắn, ...)",
  mammal: "Thú",
  amphibian: "Lưỡng cư",
  fish: "Cá",
  insect: "Côn trùng",
  other: "Khác",
};

function normalizeSpeciesType(groupValue) {
  const raw = String(groupValue || "").toLowerCase();
  if (!raw) {
    return "other";
  }
  if (raw.includes("aves") || raw.includes("bird")) {
    return "bird";
  }
  if (raw.includes("rept") || raw.includes("reptilia")) {
    return "reptile";
  }
  if (raw.includes("mamm") || raw.includes("mammalia")) {
    return "mammal";
  }
  if (raw.includes("amphib") || raw.includes("amphibia")) {
    return "amphibian";
  }
  if (
    raw.includes("fish") ||
    raw.includes("actinopterygii") ||
    raw.includes("pisces")
  ) {
    return "fish";
  }
  if (raw.includes("insect") || raw.includes("insecta")) {
    return "insect";
  }
  return "other";
}

function normalizeSummaryText(value) {
  if (!value) {
    return "Chưa có mô tả tóm tắt từ API summary.";
  }

  return String(value)
    .replace(/\\r\\n|\\n|\\r/g, "\n")
    .replace(/\r\n|\r/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function HomePage() {
  const PAGE_SIZE = 12;
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [speciesType, setSpeciesType] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [hoveredSpeciesId, setHoveredSpeciesId] = useState("");
  const [hoverPopupStyle, setHoverPopupStyle] = useState({});
  const [speciesList, setSpeciesList] = useState([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [listError, setListError] = useState("");
  const [summaryById, setSummaryById] = useState({});
  const [summaryLoadingById, setSummaryLoadingById] = useState({});

  useEffect(() => {
    let isMounted = true;

    async function loadSpecies() {
      setIsLoadingList(true);
      setListError("");
      try {
        const pageData = await fetchSpeciesList({
          keyword: query.trim(),
          page: 0,
          size: 500,
        });
        if (!isMounted) {
          return;
        }
        setSpeciesList(
          Array.isArray(pageData?.content) ? pageData.content : [],
        );
        const firstBatch = (
          Array.isArray(pageData?.content) ? pageData.content : []
        )
          .slice(0, 12)
          .map((item) => item?.heroImageUrl)
          .filter(Boolean);

        if (typeof window !== "undefined" && "requestIdleCallback" in window) {
          window.requestIdleCallback(() => {
            firstBatch.forEach((url) => prefetchImage(url));
          });
        } else {
          setTimeout(() => {
            firstBatch.forEach((url) => prefetchImage(url));
          }, 150);
        }
        setCurrentPage(1);
      } catch (error) {
        if (!isMounted) {
          return;
        }
        setListError(
          error?.response?.data?.message ||
            "Không tải được danh sách loài từ backend.",
        );
        setSpeciesList([]);
      } finally {
        if (isMounted) {
          setIsLoadingList(false);
        }
      }
    }

    loadSpecies();
    return () => {
      isMounted = false;
    };
  }, [query]);

  async function ensureSummaryLoaded(speciesId) {
    if (!speciesId || summaryById[speciesId] || summaryLoadingById[speciesId]) {
      return;
    }

    setSummaryLoadingById((prev) => ({ ...prev, [speciesId]: true }));
    try {
      const summary = await fetchSpeciesSummary(speciesId);
      setSummaryById((prev) => ({ ...prev, [speciesId]: summary }));

      prefetchImage(summary?.heroImageUrl);
      if (Array.isArray(summary?.mediaUrls)) {
        summary.mediaUrls.slice(0, 2).forEach((url) => prefetchImage(url));
      }
    } catch {
      setSummaryById((prev) => ({
        ...prev,
        [speciesId]: {
          shortDescription: "Chưa tải được mô tả nhanh cho loài này.",
        },
      }));
    } finally {
      setSummaryLoadingById((prev) => ({ ...prev, [speciesId]: false }));
    }
  }

  const filteredSpecies = useMemo(() => {
    return speciesList.filter((species) => {
      const typeOk =
        speciesType === "all" ||
        normalizeSpeciesType(species.group) === speciesType;

      if (status === "all") {
        return typeOk;
      }
      return (
        (species.conservationStatus || "").toUpperCase() === status && typeOk
      );
    });
  }, [speciesList, status, speciesType]);

  const speciesTypeOptions = useMemo(() => {
    const values = new Set(
      speciesList
        .map((item) => normalizeSpeciesType(item.group))
        .filter(Boolean),
    );
    const ordered = [
      "bird",
      "reptile",
      "mammal",
      "amphibian",
      "fish",
      "insect",
      "other",
    ];
    return ["all", ...ordered.filter((item) => values.has(item))];
  }, [speciesList]);

  const totalPages = Math.max(1, Math.ceil(filteredSpecies.length / PAGE_SIZE));

  const paginatedSpecies = useMemo(() => {
    const safePage = Math.min(currentPage, totalPages);
    const start = (safePage - 1) * PAGE_SIZE;
    return filteredSpecies.slice(start, start + PAGE_SIZE);
  }, [filteredSpecies, currentPage, totalPages]);

  useEffect(() => {
    const safePage = Math.min(currentPage, totalPages);
    if (safePage !== currentPage) {
      setCurrentPage(safePage);
    }
  }, [currentPage, totalPages]);

  useEffect(() => {
    setHoveredSpeciesId("");
  }, [currentPage, status, speciesType, query]);

  const hoveredSpecies = useMemo(
    () => paginatedSpecies.find((item) => item.id === hoveredSpeciesId) || null,
    [paginatedSpecies, hoveredSpeciesId],
  );

  const hoveredSummaryText = useMemo(() => {
    if (!hoveredSpecies) {
      return "";
    }

    if (summaryLoadingById[hoveredSpecies.id]) {
      return "Đang tải mô tả từ API summary...";
    }

    return normalizeSummaryText(
      summaryById[hoveredSpecies.id]?.shortDescription,
    );
  }, [hoveredSpecies, summaryLoadingById, summaryById]);

  function handleCardHover(speciesId, event) {
    ensureSummaryLoaded(speciesId);
    setHoveredSpeciesId(speciesId);

    const cardRect = event.currentTarget.getBoundingClientRect();
    const popupWidth = 340;
    const gap = 12;
    const openLeft = cardRect.right + popupWidth + gap > window.innerWidth - 12;

    setHoverPopupStyle({
      top: `${Math.max(12, cardRect.top)}px`,
      left: openLeft
        ? `${Math.max(12, cardRect.left - popupWidth - gap)}px`
        : `${cardRect.right + gap}px`,
      width: `${popupWidth}px`,
    });
  }

  function goToPage(page) {
    const next = Math.max(1, Math.min(totalPages, page));
    setCurrentPage(next);
  }

  return (
    <div className="app-shell">
      <header className="top-nav">
        <div className="brand-block">
          <p className="brand-eyebrow">Vietnam Wildlife</p>
          <h1>Thư viện bảo tồn động vật hoang dã</h1>
        </div>
        <nav className="anchor-nav" aria-label="Điều hướng chính">
          <a href="#library">Thư viện</a>
          <a href="#about">Dự án</a>
          <button
            className="chatbot-cta"
            onClick={() => {
              window.location.href = "/chatbot";
            }}
          >
            Mở Chatbot AI
          </button>
        </nav>
      </header>

      <section className="hero-band" id="about">
        <div className="hero-copy">
          <p className="hero-kicker">Một điểm đến cho khám phá và bảo tồn</p>
          <h2>
            Khám phá các loài động vật hoang dã Việt Nam, xem nhanh thông tin
            quan trọng và chuyển thẳng sang trợ lý AI khi cần.
          </h2>
          <div className="hero-actions">
            <a href="#library" className="primary-btn">
              Khám phá thư viện
            </a>
            <a href="/chatbot" className="secondary-btn">
              Trò chuyện với AI
            </a>
          </div>
        </div>

        <div className="hero-image-frame" aria-hidden="true">
          <img src={redBirdImage} alt="" />
        </div>
      </section>

      <section id="library" className="library-panel">
        <div className="library-toolbar">
          <input
            type="search"
            placeholder="Tìm theo tên Việt hoặc tên khoa học..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setCurrentPage(1);
            }}
          >
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          <select
            value={speciesType}
            onChange={(event) => {
              setSpeciesType(event.target.value);
              setCurrentPage(1);
            }}
          >
            {speciesTypeOptions.map((item) => (
              <option key={item} value={item}>
                {SPECIES_TYPE_LABELS[item] || item}
              </option>
            ))}
          </select>
        </div>

        {isLoadingList ? (
          <p className="library-message">
            Đang tải danh sách loài từ backend...
          </p>
        ) : null}

        {listError ? (
          <p className="library-message error">{listError}</p>
        ) : null}

        <div className="species-grid species-grid-full">
          {paginatedSpecies.map((species) => (
            <article
              key={species.id}
              className="species-card"
              onMouseEnter={(event) => handleCardHover(species.id, event)}
              onFocus={(event) => handleCardHover(species.id, event)}
              onMouseLeave={() => setHoveredSpeciesId("")}
              onBlur={() => setHoveredSpeciesId("")}
              onClick={() => navigate(`/species/${species.id}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  navigate(`/species/${species.id}`);
                }
              }}
              aria-label={`Xem chi tiết ${species.vietnameseName}`}
            >
              <figure>
                <img
                  src={species.heroImageUrl}
                  alt={species.vietnameseName}
                  loading="lazy"
                  decoding="async"
                  fetchPriority="low"
                />
                <figcaption>
                  <span>{species.vietnameseName}</span>
                  <small>{species.scientificName}</small>
                </figcaption>
              </figure>
              <div className="card-meta">
                <span
                  className={`status-tag status-${(species.conservationStatus || "dd").toLowerCase()}`}
                >
                  {(species.conservationStatus || "DD").toUpperCase()}
                </span>
                <span>
                  {SPECIES_TYPE_LABELS[normalizeSpeciesType(species.group)] ||
                    "Khác"}
                </span>
              </div>
            </article>
          ))}
        </div>

        <div className="pagination-row" aria-label="Phân trang thư viện">
          <button
            type="button"
            className="page-btn"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            Trước
          </button>
          <span className="page-indicator">
            Trang {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            className="page-btn"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
          >
            Sau
          </button>
        </div>

        {hoveredSpecies ? (
          <aside
            className="species-hover-popup"
            style={hoverPopupStyle}
            aria-live="polite"
          >
            <img
              src={
                summaryById[hoveredSpecies.id]?.heroImageUrl ||
                hoveredSpecies.heroImageUrl
              }
              alt={hoveredSpecies.vietnameseName}
              loading="lazy"
              decoding="async"
              fetchPriority="low"
            />
            <h4>{hoveredSpecies.vietnameseName}</h4>
            <p className="preview-sci-name">{hoveredSpecies.scientificName}</p>
            <p>
              <strong>Bảo tồn:</strong>{" "}
              {(
                summaryById[hoveredSpecies.id]?.conservationStatus ||
                hoveredSpecies.conservationStatus ||
                "DD"
              ).toUpperCase()}
            </p>
            <p>
              <strong>Số ảnh:</strong>{" "}
              {Array.isArray(summaryById[hoveredSpecies.id]?.mediaUrls)
                ? summaryById[hoveredSpecies.id].mediaUrls.length
                : 0}
            </p>
            <p className="preview-summary-text">{hoveredSummaryText}</p>
          </aside>
        ) : null}
      </section>
    </div>
  );
}

export default HomePage;
