export const SPECIES_SECTORS = [
  {
    slug: "chim",
    label: "Chim",
    description: "Các loài chim ghi nhận trong thư viện bảo tồn.",
  },
  {
    slug: "thu",
    label: "Thú",
    description: "Các loài thú và động vật có vú.",
  },
  {
    slug: "luong-cu",
    label: "Lưỡng cư",
    description: "Các loài lưỡng cư sống giữa nước và cạn.",
  },
  {
    slug: "khac",
    label: "Khác",
    description: "Bò sát, cá, côn trùng và các nhóm còn lại.",
  },
];

export const STATUS_LABELS = {
  all: "Tất cả mức bảo tồn",
  DD: "DD - Thiếu dữ liệu",
  LC: "LC - Ít quan tâm",
  NT: "NT - Gần đe dọa",
  VU: "VU - Sẽ nguy cấp",
  EN: "EN - Nguy cấp",
  CR: "CR - Cực kỳ nguy cấp",
};

export function getSpeciesSectorSlug(groupValue) {
  const raw = String(groupValue || "").toLowerCase();

  if (raw.includes("aves") || raw.includes("bird")) {
    return "chim";
  }

  if (raw.includes("mamm") || raw.includes("mammalia")) {
    return "thu";
  }

  if (raw.includes("amphib") || raw.includes("amphibia")) {
    return "luong-cu";
  }

  return "khac";
}

export function getSpeciesSectorBySlug(slug) {
  return SPECIES_SECTORS.find((sector) => sector.slug === slug) || null;
}

export function getSpeciesSectorLabel(groupValue) {
  const slug = getSpeciesSectorSlug(groupValue);
  return getSpeciesSectorBySlug(slug)?.label || "Khác";
}

export function groupSpeciesBySector(speciesList) {
  const grouped = Object.fromEntries(
    SPECIES_SECTORS.map((sector) => [sector.slug, []]),
  );

  for (const species of speciesList || []) {
    const slug = getSpeciesSectorSlug(species?.group);
    grouped[slug].push(species);
  }

  return grouped;
}

export function normalizeSummaryText(value) {
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
