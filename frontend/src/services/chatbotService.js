import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8080/api",
});

export async function queryChatbot({
  sessionId,
  question,
  imageUrl,
  imageRejected,
}) {
  const response = await api.post("/chatbot/query", {
    sessionId,
    question,
    imageUrl,
    imageRejected,
  });
  return response.data;
}

export async function confirmSpecies({ sessionId, speciesId }) {
  const response = await api.post("/chatbot/confirm-species", {
    sessionId,
    speciesId,
  });
  return response.data;
}
