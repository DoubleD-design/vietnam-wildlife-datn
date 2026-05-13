import { Navigate, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import SpeciesDetailPage from "./pages/SpeciesDetailPage";
import ChatbotPage from "./pages/ChatbotPage";
import SpeciesGroupPage from "./pages/SpeciesGroupPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/qa" element={<ChatbotPage />} />
      <Route path="/library/:sectorSlug" element={<SpeciesGroupPage />} />
      <Route path="/species/:speciesId" element={<SpeciesDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
