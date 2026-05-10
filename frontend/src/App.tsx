import { useEffect, useState } from 'react';
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

type MobilePanel = 'market' | 'chart' | 'signals';

function TerminalPage() {
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>('chart');

  return (
    <div className="h-screen flex flex-col bg-bg text-text1 overflow-hidden">
      <TopBar />

      {/* ── Desktop: 3-column grid ── */}
      <div className="hidden md:grid flex-1 min-h-0" style={{ gridTemplateColumns: '300px minmax(0,1fr) 300px' }}>
        <aside className="flex flex-col gap-3 p-3 border-r border-border1 overflow-hidden min-h-0">
          <ErrorBoundary label="SearchBar"><SearchBar /></ErrorBoundary>
          <ErrorBoundary label="Screener"><Screener /></ErrorBoundary>
          <ErrorBoundary label="Watchlist"><Watchlist /></ErrorBoundary>
        </aside>
        <main className="flex flex-col gap-3 p-3 overflow-hidden min-h-0">
          <ErrorBoundary label="StockHeader"><StockHeader /></ErrorBoundary>
          <div className="flex-1 min-h-0">
            <ErrorBoundary label="Chart"><Chart /></ErrorBoundary>
          </div>
        </main>
        <aside className="flex flex-col gap-3 p-3 border-l border-border1 overflow-auto min-h-0">
          <ErrorBoundary label="SignalPanel"><SignalPanel /></ErrorBoundary>
          <ErrorBoundary label="AIRecommendation"><AIRecommendation /></ErrorBoundary>
        </aside>
      </div>

      {/* ── Mobile: single panel + bottom tab bar ── */}
      <div className="flex md:hidden flex-col flex-1 min-h-0 overflow-hidden">
        {/* Active panel */}
        <div className="flex-1 overflow-auto p-3 min-h-0">
          {mobilePanel === 'market' && (
            <div className="flex flex-col gap-3">
              <ErrorBoundary label="SearchBar"><SearchBar /></ErrorBoundary>
              <ErrorBoundary label="Screener"><Screener /></ErrorBoundary>
              <ErrorBoundary label="Watchlist"><Watchlist /></ErrorBoundary>
            </div>
          )}
          {mobilePanel === 'chart' && (
            <div className="flex flex-col gap-3 h-full">
              <ErrorBoundary label="StockHeader"><StockHeader /></ErrorBoundary>
              <div className="min-h-[280px]">
                <ErrorBoundary label="Chart"><Chart /></ErrorBoundary>
              </div>
            </div>
          )}
          {mobilePanel === 'signals' && (
            <div className="flex flex-col gap-3">
              <ErrorBoundary label="SignalPanel"><SignalPanel /></ErrorBoundary>
              <ErrorBoundary label="AIRecommendation"><AIRecommendation /></ErrorBoundary>
            </div>
          )}
        </div>

        {/* Bottom tab bar */}
        <nav className="flex border-t border-border1 bg-bg2 shrink-0">
          {([
            ['market',  '📊', 'Market'],
            ['chart',   '📈', 'Chart'],
            ['signals', '🤖', 'AI'],
          ] as [MobilePanel, string, string][]).map(([id, icon, label]) => (
            <button
              key={id}
              onClick={() => setMobilePanel(id)}
              className={`flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-[10px] font-medium transition-colors
                ${mobilePanel === id ? 'text-accent' : 'text-text3'}`}
            >
              <span className="text-base leading-none">{icon}</span>
              {label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}

export default function App() {
  const setUniverse = useStore((s) => s.setUniverse);

  useEffect(() => {
    fetchUniverse()
      .then((u) => setUniverse(u.stocks))
      .catch(() => {});
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
