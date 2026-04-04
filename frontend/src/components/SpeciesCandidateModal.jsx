import { useCallback, useMemo, useRef, useState } from "react";
import { fetchSpeciesSummary } from "../services/speciesService";

function uniqueUrls(urls) {
  return Array.from(
    new Set(
      (urls || []).map((url) => String(url || "").trim()).filter(Boolean),
    ),
  );
}

export default function SpeciesCandidateModal({
  open,
  candidates = [],
  onClose,
  onSelect,
}) {
  const [hoveredSpeciesId, setHoveredSpeciesId] = useState(null);
  const [mediaBySpecies, setMediaBySpecies] = useState({});
  const [activeImageBySpecies, setActiveImageBySpecies] = useState({});
  const [popupPosition, setPopupPosition] = useState({ left: 0, top: 0 });
  const zoneRef = useRef(null);

  const hoveredCandidate = useMemo(
    () =>
      candidates.find((item) => item.speciesId === hoveredSpeciesId) || null,
    [candidates, hoveredSpeciesId],
  );

  const ensureCandidateMedia = useCallback(
    async (candidate) => {
      const speciesId = candidate?.speciesId;
      if (!speciesId || mediaBySpecies[speciesId]) {
        return;
      }

      const fallback = uniqueUrls([candidate?.heroImageUrl]);
      setMediaBySpecies((prev) => ({ ...prev, [speciesId]: fallback }));

      try {
        const summary = await fetchSpeciesSummary(speciesId);
        const mediaUrls = uniqueUrls([
          candidate?.heroImageUrl,
          ...(summary?.mediaUrls || []),
        ]);
        if (mediaUrls.length) {
          setMediaBySpecies((prev) => ({ ...prev, [speciesId]: mediaUrls }));
        }
      } catch {
        // Keep fallback image when summary API fails.
      }
    },
    [mediaBySpecies],
  );

  const popupMedia = useMemo(() => {
    if (!hoveredCandidate) {
      return [];
    }
    return (
      mediaBySpecies[hoveredCandidate.speciesId] ||
      uniqueUrls([hoveredCandidate.heroImageUrl])
    );
  }, [hoveredCandidate, mediaBySpecies]);

  const popupActiveIndex = useMemo(() => {
    if (!hoveredCandidate || popupMedia.length === 0) {
      return 0;
    }
    const stored = activeImageBySpecies[hoveredCandidate.speciesId] || 0;
    return Math.max(0, Math.min(stored, popupMedia.length - 1));
  }, [activeImageBySpecies, hoveredCandidate, popupMedia]);

  if (!open) {
    return null;
  }

  function placePopupFromCard(cardElement) {
    const zoneElement = zoneRef.current;
    if (!zoneElement || !cardElement) {
      return;
    }

    const zoneRect = zoneElement.getBoundingClientRect();
    const cardRect = cardElement.getBoundingClientRect();

    const popupWidth = 320;
    const popupHeight = 286;
    const gap = 12;

    let left = cardRect.right - zoneRect.left + gap;
    if (left + popupWidth > zoneRect.width - 8) {
      left = Math.max(8, cardRect.left - zoneRect.left - popupWidth - gap);
    }

    const centeredTop = cardRect.top - zoneRect.top + cardRect.height / 2 - popupHeight / 2;
    const maxTop = Math.max(8, zoneRect.height - popupHeight - 8);
    const top = Math.max(8, Math.min(maxTop, centeredTop));

    setPopupPosition({ left, top });
  }

  return (
    <div className="candidate-modal-overlay" role="dialog" aria-modal="true">
      <div className="candidate-modal-shell">
        <header className="candidate-modal-header">
          <div>
            <h3>Chọn loài phù hợp</h3>
            <p>
              Di chuột vào thẻ để xem bộ ảnh. Rời cả vùng modal thì popup sẽ tự
              ẩn.
            </p>
          </div>
          <button
            type="button"
            className="candidate-modal-close"
            onClick={onClose}
          >
            Đóng
          </button>
        </header>

        <div
          ref={zoneRef}
          className="candidate-picker-zone"
          onMouseLeave={() => {
            setHoveredSpeciesId(null);
            setPopupPosition({ left: 0, top: 0 });
          }}
        >
          <div className="candidate-grid">
            {candidates.map((candidate) => {
              const speciesId = candidate.speciesId;
              const active = speciesId === hoveredSpeciesId;

              return (
                <button
                  key={speciesId}
                  type="button"
                  className={`candidate-card ${active ? "active" : ""}`}
                  onMouseEnter={(event) => {
                    setHoveredSpeciesId(speciesId);
                    ensureCandidateMedia(candidate);
                    placePopupFromCard(event.currentTarget);
                  }}
                  onFocus={(event) => {
                    setHoveredSpeciesId(speciesId);
                    ensureCandidateMedia(candidate);
                    placePopupFromCard(event.currentTarget);
                  }}
                  onClick={() => onSelect?.(candidate)}
                >
                  <img
                    src={candidate.heroImageUrl}
                    alt={candidate.vietnameseName || candidate.scientificName}
                  />
                  <div className="candidate-card-info">
                    <strong>{candidate.vietnameseName || "Chưa rõ tên"}</strong>
                    <small>{candidate.scientificName || ""}</small>
                  </div>
                </button>
              );
            })}
          </div>

          {hoveredCandidate && popupMedia.length > 0 ? (
            <aside
              className="candidate-hover-popup"
              style={{
                left: `${popupPosition.left}px`,
                top: `${popupPosition.top}px`,
              }}
              onMouseEnter={() =>
                setHoveredSpeciesId(hoveredCandidate.speciesId)
              }
            >
              <img
                className="candidate-hover-main"
                src={popupMedia[popupActiveIndex]}
                alt={
                  hoveredCandidate.vietnameseName ||
                  hoveredCandidate.scientificName
                }
              />
              <div className="candidate-hover-thumbs">
                {popupMedia.slice(0, 8).map((url, index) => (
                  <button
                    key={`${hoveredCandidate.speciesId}-${url}-${index}`}
                    type="button"
                    className={`candidate-hover-thumb ${index === popupActiveIndex ? "active" : ""}`}
                    onClick={() => {
                      setActiveImageBySpecies((prev) => ({
                        ...prev,
                        [hoveredCandidate.speciesId]: index,
                      }));
                    }}
                    aria-label={`Xem anh ${index + 1}`}
                  >
                    <img src={url} alt="thumb" />
                  </button>
                ))}
              </div>
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}
