import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SpeciesCard from "../components/SpeciesCard";
import SpeciesHoverPreview from "../components/SpeciesHoverPreview";
import redBirdImage from "../assets/red_bird.jpg";
import {
  fetchSpeciesList,
  fetchSpeciesSummary,
} from "../services/speciesService";
import { SPECIES_SECTORS } from "../utils/speciesGrouping";
import "../App.css";

const HOME_SECTOR_CARD_LIMIT = 16;
const HOME_SEARCH_RESULT_LIMIT = 24;

function HomePage() {
  const navigate = useNavigate();
  const carouselRefs = useRef({});
  const [query, setQuery] = useState("");
  const [hoveredSpeciesId, setHoveredSpeciesId] = useState("");
  const [hoverPopupStyle, setHoverPopupStyle] = useState({});
  const [sectorSpeciesBySlug, setSectorSpeciesBySlug] = useState({});
  const [sectorTotalBySlug, setSectorTotalBySlug] = useState({});
  const [searchResults, setSearchResults] = useState([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [listError, setListError] = useState("");
  const [summaryById, setSummaryById] = useState({});
  const [summaryLoadingById, setSummaryLoadingById] = useState({});

  const trimmedQuery = query.trim();
  const isSearching = trimmedQuery.length > 0;

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    async function loadSpecies() {
      setIsLoadingList(true);
      setListError("");
      try {
        if (isSearching) {
          const pageData = await fetchSpeciesList({
            keyword: trimmedQuery,
            page: 0,
            size: HOME_SEARCH_RESULT_LIMIT,
            signal: controller.signal,
          });
          if (!isMounted) {
            return;
          }

          const content = Array.isArray(pageData?.content)
            ? pageData.content
            : [];
          setSearchResults(content);
          setSearchTotal(Number(pageData?.totalElements) || content.length);
          return;
        }

        const sectorResponses = await Promise.all(
          SPECIES_SECTORS.map(async (sector) => {
            const pageData = await fetchSpeciesList({
              sectorSlug: sector.slug,
              page: 0,
              size: HOME_SECTOR_CARD_LIMIT,
              signal: controller.signal,
            });
            return [sector.slug, pageData];
          }),
        );
        if (!isMounted) {
          return;
        }

        const nextSpeciesBySlug = {};
        const nextTotalBySlug = {};
        sectorResponses.forEach(([slug, pageData]) => {
          const content = Array.isArray(pageData?.content)
            ? pageData.content
            : [];
          nextSpeciesBySlug[slug] = content;
          nextTotalBySlug[slug] = Number(pageData?.totalElements) || content.length;
        });
        setSectorSpeciesBySlug(nextSpeciesBySlug);
        setSectorTotalBySlug(nextTotalBySlug);
      } catch (error) {
        if (error?.code === "ERR_CANCELED" || controller.signal.aborted) {
          return;
        }
        if (!isMounted) {
          return;
        }
        setListError(
          error?.response?.data?.message ||
            "Không tải được danh sách loài từ backend.",
        );
        setSectorSpeciesBySlug({});
        setSectorTotalBySlug({});
        setSearchResults([]);
        setSearchTotal(0);
      } finally {
        if (isMounted) {
          setIsLoadingList(false);
        }
      }
    }

    loadSpecies();
    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [isSearching, trimmedQuery]);

  useEffect(() => {
    setHoveredSpeciesId("");
  }, [trimmedQuery]);

  async function ensureSummaryLoaded(speciesId) {
    if (!speciesId || summaryById[speciesId] || summaryLoadingById[speciesId]) {
      return;
    }

    setSummaryLoadingById((prev) => ({ ...prev, [speciesId]: true }));
    try {
      const summary = await fetchSpeciesSummary(speciesId);
      setSummaryById((prev) => ({ ...prev, [speciesId]: summary }));
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

  const activeSpeciesList = useMemo(() => {
    if (isSearching) {
      return searchResults;
    }

    return SPECIES_SECTORS.flatMap(
      (sector) => sectorSpeciesBySlug[sector.slug] || [],
    );
  }, [isSearching, searchResults, sectorSpeciesBySlug]);

  const visibleSearchResults = useMemo(
    () => searchResults.slice(0, HOME_SEARCH_RESULT_LIMIT),
    [searchResults],
  );

  const hasMoreSearchResults = searchTotal > visibleSearchResults.length;

  const hoveredSpecies = useMemo(
    () => activeSpeciesList.find((item) => item.id === hoveredSpeciesId) || null,
    [activeSpeciesList, hoveredSpeciesId],
  );

  function handleCardHover(species, event) {
    const speciesId = species?.id;
    if (!speciesId) {
      return;
    }

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

  function handleOpenSpecies(species) {
    if (species?.id) {
      navigate(`/species/${species.id}`);
    }
  }

  function scrollCarousel(key, direction) {
    const element = carouselRefs.current[key];
    if (!element) {
      return;
    }

    const distance = Math.max(320, element.clientWidth * 0.82);
    element.scrollBy({
      left: direction * distance,
      behavior: "smooth",
    });
  }

  function renderSpeciesRail(items, railKey, emptyText, priorityCount = 0) {
    if (items.length === 0) {
      return <p className="library-empty-message">{emptyText}</p>;
    }

    return (
      <div
        className="species-carousel"
        ref={(node) => {
          carouselRefs.current[railKey] = node;
        }}
      >
        {items.map((species, index) => (
          <SpeciesCard
            key={species.id}
            species={species}
            className="carousel-card"
            priority={index < priorityCount}
            onHover={handleCardHover}
            onLeave={() => setHoveredSpeciesId("")}
            onOpen={handleOpenSpecies}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="app-shell" data-testid="home-shell">
      <header className="top-nav">
        <div className="brand-block">
          <p className="brand-eyebrow">Vietnam Wildlife</p>
          <h1>Thư viện bảo tồn động vật hoang dã</h1>
        </div>
        <nav className="anchor-nav" aria-label="Điều hướng chính">
          <a href="#library">Thư viện</a>
          <button
            className="chatbot-cta"
            onClick={() => {
              navigate("/qa");
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
            <a href="/qa" className="secondary-btn">
              Trò chuyện với AI
            </a>
          </div>
        </div>

        <div className="hero-image-frame" aria-hidden="true">
          <img src={redBirdImage} alt="" />
        </div>
      </section>

      <section id="library" className="library-panel library-panel-modern">
        <div className="library-intro-row">
          <div>
            <p className="library-eyebrow">Thư viện theo nhóm loài</p>
            <h2>Khám phá nhanh theo loài</h2>
          </div>

          <label className="library-search-control">
            <span className="search-icon" aria-hidden="true">
              ⌕
            </span>
            <input
              type="search"
              placeholder="Tìm theo tên Việt hoặc tên khoa học..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {isSearching ? (
              <button
                type="button"
                className="library-clear-search"
                onClick={() => setQuery("")}
                aria-label="Xóa tìm kiếm"
              >
                ×
              </button>
            ) : null}
          </label>
        </div>

        {isLoadingList ? (
          <p className="library-message">
            Đang tải danh sách loài từ backend...
          </p>
        ) : null}

        {listError ? (
          <p className="library-message error">{listError}</p>
        ) : null}

        {!isLoadingList && !listError && isSearching ? (
          <section className="search-results-panel">
            <div className="sector-header">
              <div>
                <p className="sector-kicker">Kết quả tìm kiếm</p>
                <h3>{`Kết quả cho "${trimmedQuery}"`}</h3>
              </div>
              <div className="sector-actions">
                <button
                  type="button"
                  className="carousel-arrow"
                  onClick={() => scrollCarousel("search-results", -1)}
                  aria-label="Trượt kết quả sang trái"
                >
                  ‹
                </button>
                <button
                  type="button"
                  className="carousel-arrow"
                  onClick={() => scrollCarousel("search-results", 1)}
                  aria-label="Trượt kết quả sang phải"
                >
                  ›
                </button>
              </div>
            </div>
            {renderSpeciesRail(
              visibleSearchResults,
              "search-results",
              "Không tìm thấy loài nào phù hợp với từ khóa này.",
              4,
            )}
            {hasMoreSearchResults ? (
              <p className="library-result-note">
                Đang hiển thị {visibleSearchResults.length} kết quả đầu tiên.
                Hãy nhập từ khóa cụ thể hơn nếu bạn muốn thu hẹp danh sách.
              </p>
            ) : null}
          </section>
        ) : null}

        {!isLoadingList && !listError && !isSearching
          ? SPECIES_SECTORS.map((sector) => {
              const items = sectorSpeciesBySlug[sector.slug] || [];
              const totalItems = sectorTotalBySlug[sector.slug] || items.length;
              return (
                <section className="species-sector" key={sector.slug}>
                  <div className="sector-header">
                    <div>
                      <p className="sector-kicker">{sector.description}</p>
                      <h3>{sector.label}</h3>
                      {totalItems > items.length ? (
                        <p className="sector-count-note">
                          Hiển thị {items.length} / {totalItems} loài nổi
                          bật
                        </p>
                      ) : null}
                    </div>
                    <div className="sector-actions">
                      <Link
                        className="sector-view-all"
                        to={`/library/${sector.slug}`}
                      >
                        Xem tất cả
                      </Link>
                      <button
                        type="button"
                        className="carousel-arrow"
                        onClick={() => scrollCarousel(sector.slug, -1)}
                        aria-label={`Trượt ${sector.label} sang trái`}
                      >
                        ‹
                      </button>
                      <button
                        type="button"
                        className="carousel-arrow"
                        onClick={() => scrollCarousel(sector.slug, 1)}
                        aria-label={`Trượt ${sector.label} sang phải`}
                      >
                        ›
                      </button>
                    </div>
                  </div>
                  {renderSpeciesRail(
                    items,
                    sector.slug,
                    `Chưa có loài nào trong nhóm ${sector.label}.`,
                    sector.slug === SPECIES_SECTORS[0].slug ? 4 : 0,
                  )}
                </section>
              );
            })
          : null}

        <SpeciesHoverPreview
          species={hoveredSpecies}
          summary={summaryById[hoveredSpecies?.id]}
          isLoading={Boolean(summaryLoadingById[hoveredSpecies?.id])}
          style={hoverPopupStyle}
        />
      </section>
    </div>
  );
}

export default HomePage;
