import { Navigate, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import SpeciesDetailPage from "./pages/SpeciesDetailPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/species/:speciesId" element={<SpeciesDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
