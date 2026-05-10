import { useEffect } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { useStore } from './store/useStore';
import { fetchUniverse } from './api/client';
import TopBar from './components/TopBar';
import SearchBar from './components/SearchBar';
import Screener from './components/Screener';
import Watchlist from './components/Watchlist';
import StockHeader from './components/StockHeader';
import Chart from './components/Chart';
import SignalPanel from './components/SignalPanel';
import AIRecommendation from './components/AIRecommendation';
import { ErrorBoundary } from './components/ErrorBoundary';
import BacktestPage from './pages/BacktestPage';
import PaperTradingPage from './pages/PaperTradingPage';

function TerminalPage() {
  return (
    <div className="h-screen flex flex-col bg-bg text-text1 overflow-hidden">
      <TopBar />

      <div className="flex-1 grid min-h-0" style={{ gridTemplateColumns: '320px minmax(0,1fr) 320px' }}>
        {/* LEFT */}
        <aside className="flex flex-col gap-3 p-3 border-r border-border1 overflow-hidden min-h-0">
          <ErrorBoundary label="SearchBar"><SearchBar /></ErrorBoundary>
          <ErrorBoundary label="Screener"><Screener /></ErrorBoundary>
          <ErrorBoundary label="Watchlist"><Watchlist /></ErrorBoundary>
        </aside>

        {/* CENTER */}
        <main className="flex flex-col gap-3 p-3 overflow-hidden min-h-0">
          <ErrorBoundary label="StockHeader"><StockHeader /></ErrorBoundary>
          <div className="flex-1 min-h-0">
            <ErrorBoundary label="Chart"><Chart /></ErrorBoundary>
          </div>
        </main>

        {/* RIGHT */}
        <aside className="flex flex-col gap-3 p-3 border-l border-border1 overflow-auto min-h-0">
          <ErrorBoundary label="SignalPanel"><SignalPanel /></ErrorBoundary>
          <ErrorBoundary label="AIRecommendation"><AIRecommendation /></ErrorBoundary>
        </aside>
      </div>
    </div>
  );
}

export default function App() {
  const setUniverse = useStore((s) => s.setUniverse);

  useEffect(() => {
    fetchUniverse()
      .then((u) => setUniverse(u.stocks))
      .catch(() => { /* universe stays empty; SearchBar will show empty results */ });
  }, [setUniverse]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<TerminalPage />} />
        <Route path="/backtest" element={<ErrorBoundary label="BacktestPage"><BacktestPage /></ErrorBoundary>} />
        <Route path="/paper-trading" element={<ErrorBoundary label="PaperTradingPage"><PaperTradingPage /></ErrorBoundary>} />
      </Routes>
    </BrowserRouter>
  );
}
