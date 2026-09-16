import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './Home';
import SurveyPage from './survey/SurveyPage';
import AnalyzePage from './survey/AnalyzePage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/survey" element={<SurveyPage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
      </Routes>
    </BrowserRouter>
  );
}
