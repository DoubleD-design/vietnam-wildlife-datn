import { useEffect, useRef, useState } from "react";
import { getSpeciesSectorLabel } from "../utils/speciesGrouping";

export default function SpeciesCard({
  species,
  className = "",
  onOpen,
  onHover,
  onLeave,
  priority = false,
}) {
  const imageFrameRef = useRef(null);
  const imageUrl = species?.thumbnailUrl || species?.heroImageUrl || "";
  const [loadedImageUrl, setLoadedImageUrl] = useState("");
  const vietnameseName = species?.vietnameseName || "Chưa rõ tên";
  const scientificName = species?.scientificName || "";
  const conservationStatus = (species?.conservationStatus || "DD").toUpperCase();
  const supportsLazyObserver =
    typeof window !== "undefined" && "IntersectionObserver" in window;
  const shouldLoadImage =
    Boolean(imageUrl) &&
    (priority || !supportsLazyObserver || loadedImageUrl === imageUrl);
  const imageLoading = priority ? "eager" : "lazy";
  const imageFetchPriority = priority ? "high" : "low";

  useEffect(() => {
    const frame = imageFrameRef.current;
    if (!frame || !imageUrl || !supportsLazyObserver || shouldLoadImage) {
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setLoadedImageUrl(imageUrl);
          observer.disconnect();
        }
      },
      {
        root: null,
        rootMargin: "120px 160px",
        threshold: 0.01,
      },
    );

    observer.observe(frame);
    return () => observer.disconnect();
  }, [imageUrl, shouldLoadImage, supportsLazyObserver]);

  function handleOpen() {
    onOpen?.(species);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleOpen();
    }
  }

  return (
    <article
      className={`species-card ${className}`.trim()}
      onMouseEnter={(event) => onHover?.(species, event)}
      onFocus={(event) => onHover?.(species, event)}
      onMouseLeave={onLeave}
      onBlur={onLeave}
      onClick={handleOpen}
      role="button"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-label={`Xem chi tiết ${vietnameseName}`}
    >
      <figure>
        <div className="species-image-frame" ref={imageFrameRef}>
          {shouldLoadImage && imageUrl ? (
            <img
              className="species-card-image"
              src={imageUrl}
              alt={vietnameseName}
              loading={imageLoading}
              decoding="async"
              fetchPriority={imageFetchPriority}
            />
          ) : (
            <div className="species-image-placeholder" aria-hidden="true" />
          )}
        </div>
        <figcaption>
          <span>{vietnameseName}</span>
          <small>{scientificName}</small>
        </figcaption>
      </figure>
      <div className="card-meta">
        <span className={`status-tag status-${conservationStatus.toLowerCase()}`}>
          {conservationStatus}
        </span>
        <span>{getSpeciesSectorLabel(species?.group)}</span>
      </div>
    </article>
  );
}
