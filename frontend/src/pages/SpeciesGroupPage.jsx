import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FirstPageIcon from "@mui/icons-material/FirstPage";
import LastPageIcon from "@mui/icons-material/LastPage";
import QueryStatsIcon from "@mui/icons-material/QueryStats";
import SpeciesCard from "../components/SpeciesCard";
import SpeciesHoverPreview from "../components/SpeciesHoverPreview";
import {
  fetchSpeciesList,
  fetchSpeciesSummary,
  prefetchImage,
} from "../services/speciesService";
import {
  STATUS_LABELS,
  getSpeciesSectorBySlug,
} from "../utils/speciesGrouping";
import "../App.css";

const PAGE_SIZE = 8;
const EMPTY_PAGE_DATA = {
  content: [],
  page: 0,
  size: PAGE_SIZE,
  totalElements: 0,
  totalPages: 0,
};
const VALID_STATUS_VALUES = new Set(Object.keys(STATUS_LABELS));

function formatNumber(value) {
  return new Intl.NumberFormat("vi-VN").format(Number(value) || 0);
}

function parsePageParam(value) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function normalizeStatusParam(value) {
  const normalized = String(value || "all").toUpperCase();
  return VALID_STATUS_VALUES.has(normalized) ? normalized : "all";
}

function normalizePageData(pageData, requestedPage) {
  return {
    content: Array.isArray(pageData?.content) ? pageData.content : [],
    page: Number.isFinite(Number(pageData?.page))
      ? Number(pageData.page)
      : requestedPage - 1,
    size: Number.isFinite(Number(pageData?.size))
      ? Number(pageData.size)
      : PAGE_SIZE,
    totalElements: Number(pageData?.totalElements) || 0,
    totalPages: Number(pageData?.totalPages) || 0,
  };
}

function buildCacheKey({ sectorSlug, status, query, page }) {
  return [sectorSlug, status, query.trim().toLowerCase(), page, PAGE_SIZE].join(
    "|",
  );
}

function buildPageWindow(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set([
    1,
    totalPages,
    currentPage - 1,
    currentPage,
    currentPage + 1,
  ]);
  const sortedPages = [...pages]
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((a, b) => a - b);

  return sortedPages.flatMap((page, index) => {
    const previous = sortedPages[index - 1];
    if (index > 0 && page - previous > 1) {
      return ["ellipsis", page];
    }
    return [page];
  });
}

function getCardImageUrl(species) {
  return species?.thumbnailUrl || species?.heroImageUrl || "";
}

function SpeciesGroupPage() {
  const { sectorSlug } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const sector = getSpeciesSectorBySlug(sectorSlug);
  const urlQuery = (searchParams.get("q") || "").trim();
  const urlStatus = normalizeStatusParam(searchParams.get("status"));
  const urlPage = parsePageParam(searchParams.get("page"));

  const [query, setQuery] = useState(urlQuery);
  const [jumpPage, setJumpPage] = useState("");
  const [hoveredSpeciesId, setHoveredSpeciesId] = useState("");
  const [hoverPopupStyle, setHoverPopupStyle] = useState({});
  const [pageData, setPageData] = useState(EMPTY_PAGE_DATA);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [listError, setListError] = useState("");
  const [summaryById, setSummaryById] = useState({});
  const [summaryLoadingById, setSummaryLoadingById] = useState({});
  const pageCacheRef = useRef(new Map());
  const activeRequestRef = useRef(null);

  const totalPagesFromApi = Number(pageData.totalPages) || 0;
  const totalPages = Math.max(1, totalPagesFromApi);
  const visibleSpecies = pageData.content;
  const totalElements = Number(pageData.totalElements) || 0;
  const currentResultStart = totalElements
    ? pageData.page * pageData.size + 1
    : 0;
  const currentResultEnd = totalElements
    ? Math.min(currentResultStart + visibleSpecies.length - 1, totalElements)
    : 0;
  const activeStatusLabel = STATUS_LABELS[urlStatus] || STATUS_LABELS.all;
  const pageItems = useMemo(
    () => buildPageWindow(Math.min(urlPage, totalPages), totalPages),
    [totalPages, urlPage],
  );
  const mosaicSpecies = visibleSpecies.slice(0, 4);

  const updateUrlParams = useCallback(
    ({ q = urlQuery, status = urlStatus, page = urlPage }, options = {}) => {
      const params = new URLSearchParams();
      const nextQuery = String(q || "").trim();
      const nextStatus = normalizeStatusParam(status);
      const nextPage = Math.max(1, Number.parseInt(page, 10) || 1);

      if (nextQuery) {
        params.set("q", nextQuery);
      }
      if (nextStatus !== "all") {
        params.set("status", nextStatus);
      }
      if (nextPage > 1) {
        params.set("page", String(nextPage));
      }

      setSearchParams(params, { replace: Boolean(options.replace) });
    },
    [setSearchParams, urlPage, urlQuery, urlStatus],
  );

  const fetchPageForParams = useCallback(
    async (pageNumber, { signal } = {}) => {
      const safePage = Math.max(1, Number.parseInt(pageNumber, 10) || 1);
      const cacheKey = buildCacheKey({
        sectorSlug,
        status: urlStatus,
        query: urlQuery,
        page: safePage,
      });
      const cached = pageCacheRef.current.get(cacheKey);
      if (cached) {
        return cached;
      }

      const response = await fetchSpeciesList({
        keyword: urlQuery,
        page: safePage - 1,
        size: PAGE_SIZE,
        sectorSlug,
        conservationStatus: urlStatus,
        signal,
      });
      const normalized = normalizePageData(response, safePage);
      pageCacheRef.current.set(cacheKey, normalized);
      return normalized;
    },
    [sectorSlug, urlQuery, urlStatus],
  );

  useEffect(() => {
    setQuery(urlQuery);
    setJumpPage("");
    setHoveredSpeciesId("");
  }, [sectorSlug, urlQuery, urlStatus, urlPage]);

  useEffect(() => {
    if (!sector) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      const nextQuery = query.trim();
      if (nextQuery !== urlQuery) {
        updateUrlParams({
          q: nextQuery,
          status: urlStatus,
          page: 1,
        }, { replace: true });
      }
    }, 300);

    return () => window.clearTimeout(timer);
  }, [query, sector, updateUrlParams, urlQuery, urlStatus]);

  useEffect(() => {
    if (!sector) {
      return undefined;
    }

    const cacheKey = buildCacheKey({
      sectorSlug,
      status: urlStatus,
      query: urlQuery,
      page: urlPage,
    });
    const cached = pageCacheRef.current.get(cacheKey);
    if (cached) {
      setPageData(cached);
      setIsLoadingList(false);
      setListError("");
      return undefined;
    }

    activeRequestRef.current?.abort();
    const controller = new AbortController();
    activeRequestRef.current = controller;
    setIsLoadingList(true);
    setListError("");
    setPageData({ ...EMPTY_PAGE_DATA, page: urlPage - 1 });

    fetchPageForParams(urlPage, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setPageData(data);
        }
      })
      .catch((error) => {
        if (error?.code === "ERR_CANCELED" || controller.signal.aborted) {
          return;
        }

        setListError(
          error?.response?.data?.message ||
            "Không tải được danh sách loài từ backend.",
        );
        setPageData({ ...EMPTY_PAGE_DATA, page: urlPage - 1 });
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingList(false);
        }
      });

    return () => controller.abort();
  }, [fetchPageForParams, sector, sectorSlug, urlPage, urlQuery, urlStatus]);

  useEffect(() => {
    if (isLoadingList || listError) {
      return;
    }

    if (totalPagesFromApi === 0 && urlPage !== 1) {
      updateUrlParams({ page: 1 }, { replace: true });
      return;
    }

    if (totalPagesFromApi > 0 && urlPage > totalPagesFromApi) {
      updateUrlParams({ page: totalPagesFromApi }, { replace: true });
    }
  }, [isLoadingList, listError, totalPagesFromApi, updateUrlParams, urlPage]);

  useEffect(() => {
    if (!sector || isLoadingList || listError || totalPagesFromApi <= 1) {
      return;
    }

    const adjacentPages = [urlPage - 1, urlPage + 1].filter(
      (page) => page >= 1 && page <= totalPagesFromApi,
    );

    adjacentPages.forEach((page) => {
      fetchPageForParams(page)
        .then((data) => {
          data.content.slice(0, 4).forEach((species) => {
            prefetchImage(getCardImageUrl(species));
          });
        })
        .catch(() => {
          // Prefetch is opportunistic; the active page request owns user-visible errors.
        });
    });
  }, [
    fetchPageForParams,
    isLoadingList,
    listError,
    sector,
    totalPagesFromApi,
    urlPage,
  ]);

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

  const hoveredSpecies = useMemo(
    () => visibleSpecies.find((item) => item.id === hoveredSpeciesId) || null,
    [hoveredSpeciesId, visibleSpecies],
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

  function goToPage(page, options = {}) {
    const maxPage = Math.max(1, totalPagesFromApi || totalPages);
    const next = Math.max(1, Math.min(maxPage, Number.parseInt(page, 10) || 1));
    setHoveredSpeciesId("");
    updateUrlParams({ q: query.trim(), page: next }, options);
  }

  function handleStatusChange(event) {
    updateUrlParams({
      q: query.trim(),
      status: event.target.value,
      page: 1,
    });
  }

  function handleClearSearch() {
    setQuery("");
    updateUrlParams({ q: "", status: urlStatus, page: 1 });
  }

  function handleJumpSubmit(event) {
    event.preventDefault();
    goToPage(jumpPage);
    setJumpPage("");
  }

  if (!sector) {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="group-page-wrap">
      <header className="group-page-header group-hero">
        <div className="group-hero-content">
          <Link className="detail-back-link group-back-link" to="/">
            ← Quay lại trang chủ
          </Link>
          <p className="library-eyebrow">Thư viện nhóm loài</p>
          <h1>{sector.label}</h1>
          <p className="group-hero-description">{sector.description}</p>

          <div className="group-hero-chips" aria-label="Thống kê nhóm loài">
            <span className="group-hero-chip">
              <QueryStatsIcon fontSize="small" />
              {formatNumber(totalElements)} loài
            </span>
            <span className="group-hero-chip">
              {formatNumber(totalPagesFromApi)} trang
            </span>
            <span className="group-hero-chip">{activeStatusLabel}</span>
            <span className="group-hero-chip">
              {currentResultStart
                ? `${formatNumber(currentResultStart)}-${formatNumber(currentResultEnd)} đang hiển thị`
                : "Chưa có kết quả"}
            </span>
          </div>

          <div className="group-hero-cta">
            <Link className="group-hero-chatbot-btn" to="/qa">
              <AutoAwesomeIcon fontSize="small" />
              Hỏi AI về nhóm {sector.label}
            </Link>
            <span>Đặt câu hỏi về nhận diện, môi trường sống và bảo tồn.</span>
          </div>
        </div>

        <div className="group-hero-mosaic" aria-hidden="true">
          {mosaicSpecies.length > 0
            ? mosaicSpecies.map((species, index) => {
                const imageUrl = getCardImageUrl(species);
                return (
                  <div className="group-hero-mosaic-card" key={species.id}>
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt=""
                        loading={index < 2 ? "eager" : "lazy"}
                        decoding="async"
                      />
                    ) : (
                      <div className="group-hero-mosaic-placeholder" />
                    )}
                    <span>{species.vietnameseName || species.scientificName}</span>
                  </div>
                );
              })
            : Array.from({ length: 4 }, (_, index) => (
                <div className="group-hero-mosaic-card" key={index}>
                  <div className="group-hero-mosaic-placeholder" />
                </div>
              ))}
        </div>
      </header>

      <section className="library-panel group-library-panel">
        <div className="group-toolbar">
          <label className="library-search-control group-search-control">
            <span className="search-icon" aria-hidden="true">
              ⌕
            </span>
            <input
              type="search"
              placeholder={`Tìm trong nhóm ${sector.label}...`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {query.trim() || urlQuery ? (
              <button
                type="button"
                className="library-clear-search"
                onClick={handleClearSearch}
                aria-label="Xóa tìm kiếm"
              >
                ×
              </button>
            ) : null}
          </label>

          <select value={urlStatus} onChange={handleStatusChange}>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {isLoadingList ? (
          <p className="library-message">
            Đang tải trang {formatNumber(urlPage)}...
          </p>
        ) : null}

        {listError ? (
          <p className="library-message error">{listError}</p>
        ) : null}

        {!isLoadingList && !listError && totalElements === 0 ? (
          <p className="library-empty-message">
            Không có loài nào phù hợp với bộ lọc hiện tại.
          </p>
        ) : null}

        <div className="species-grid species-grid-full">
          {visibleSpecies.map((species, index) => (
            <SpeciesCard
              key={species.id}
              species={species}
              priority={index < 4}
              onHover={handleCardHover}
              onLeave={() => setHoveredSpeciesId("")}
              onOpen={(item) => navigate(`/species/${item.id}`)}
            />
          ))}
        </div>

        {totalPagesFromApi > 1 ? (
          <nav className="pagination-row" aria-label="Phân trang thư viện">
            <button
              type="button"
              className="page-btn page-icon-btn"
              onClick={() => goToPage(1)}
              disabled={urlPage <= 1}
              aria-label="Về trang đầu"
            >
              <FirstPageIcon fontSize="small" />
            </button>
            <button
              type="button"
              className="page-btn page-icon-btn"
              onClick={() => goToPage(urlPage - 1)}
              disabled={urlPage <= 1}
              aria-label="Trang trước"
            >
              <ChevronLeftIcon fontSize="small" />
            </button>

            <div className="page-number-window">
              {pageItems.map((item, index) =>
                item === "ellipsis" ? (
                  <span className="page-ellipsis" key={`ellipsis-${index}`}>
                    ...
                  </span>
                ) : (
                  <button
                    type="button"
                    className={`page-btn page-number-btn ${
                      item === urlPage ? "active" : ""
                    }`}
                    onClick={() => goToPage(item)}
                    aria-current={item === urlPage ? "page" : undefined}
                    key={item}
                  >
                    {item}
                  </button>
                ),
              )}
            </div>

            <button
              type="button"
              className="page-btn page-icon-btn"
              onClick={() => goToPage(urlPage + 1)}
              disabled={urlPage >= totalPagesFromApi}
              aria-label="Trang sau"
            >
              <ChevronRightIcon fontSize="small" />
            </button>
            <button
              type="button"
              className="page-btn page-icon-btn"
              onClick={() => goToPage(totalPagesFromApi)}
              disabled={urlPage >= totalPagesFromApi}
              aria-label="Về trang cuối"
            >
              <LastPageIcon fontSize="small" />
            </button>

            <form className="page-jump-form" onSubmit={handleJumpSubmit}>
              <label htmlFor="page-jump-input">Đi tới trang</label>
              <input
                id="page-jump-input"
                type="number"
                min="1"
                max={totalPagesFromApi}
                inputMode="numeric"
                placeholder={String(urlPage)}
                value={jumpPage}
                onChange={(event) => setJumpPage(event.target.value)}
              />
            </form>
          </nav>
        ) : null}

        <SpeciesHoverPreview
          species={hoveredSpecies}
          summary={summaryById[hoveredSpecies?.id]}
          isLoading={Boolean(summaryLoadingById[hoveredSpecies?.id])}
          style={hoverPopupStyle}
        />
      </section>
    </main>
  );
}

export default SpeciesGroupPage;
