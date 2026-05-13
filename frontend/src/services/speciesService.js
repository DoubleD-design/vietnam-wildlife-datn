import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8080/api",
});

const prefetchedImageUrls = new Set();

export function prefetchImage(url) {
  const normalized = String(url || "").trim();
  if (!normalized || prefetchedImageUrls.has(normalized)) {
    return;
  }

  prefetchedImageUrls.add(normalized);
  const image = new Image();
  image.decoding = "async";
  image.loading = "eager";
  image.src = normalized;
}

export async function fetchSpeciesList({
  keyword = "",
  page = 0,
  size = 48,
  sectorSlug = "",
  conservationStatus = "",
  signal,
} = {}) {
  const params = {
    keyword,
    page,
    size,
  };

  if (sectorSlug) {
    params.sectorSlug = sectorSlug;
  }

  if (conservationStatus && conservationStatus !== "all") {
    params.conservationStatus = conservationStatus;
  }

  const response = await api.get("/species", {
    params,
    signal,
  });
  return response.data;
}

export async function fetchSpeciesSummary(speciesId) {
  const response = await api.get(`/species/${speciesId}/summary`);
  return response.data;
}

export async function fetchSpeciesScientificProfile(speciesId) {
  const response = await api.get(`/species/${speciesId}/scientific-profile`);
  return response.data;
}
