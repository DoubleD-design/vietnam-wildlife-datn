import { normalizeSummaryText } from "../utils/speciesGrouping";

export default function SpeciesHoverPreview({
  species,
  summary,
  isLoading,
  style,
}) {
  if (!species) {
    return null;
  }

  const mediaCount = Array.isArray(summary?.mediaUrls)
    ? summary.mediaUrls.length
    : 0;
  const conservationStatus = (
    summary?.conservationStatus ||
    species.conservationStatus ||
    "DD"
  ).toUpperCase();

  return (
    <aside className="species-hover-popup" style={style} aria-live="polite">
      <img
        src={summary?.heroImageUrl || species.heroImageUrl}
        alt={species.vietnameseName}
        loading="lazy"
        decoding="async"
        fetchPriority="low"
      />
      <h4>{species.vietnameseName}</h4>
      <p className="preview-sci-name">{species.scientificName}</p>
      <p>
        <strong>Bảo tồn:</strong> {conservationStatus}
      </p>
      <p>
        <strong>Số ảnh:</strong> {mediaCount}
      </p>
      <p className="preview-summary-text">
        {isLoading
          ? "Đang tải mô tả từ API summary..."
          : normalizeSummaryText(summary?.shortDescription)}
      </p>
    </aside>
  );
}
