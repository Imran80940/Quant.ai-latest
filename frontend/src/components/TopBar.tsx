import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchIndices } from '../api/client';
import { useStore } from '../store/useStore';
import type { IndexLevel, IndicesResponse } from '../types';
import { fmtPct, isMarketOpen, istClock, colorForChange } from '../utils';

const NAV_LINKS: { to: string; label: string }[] = [
  { to: '/',              label: 'Terminal' },
  { to: '/backtest',      label: 'Backtest' },
  { to: '/paper-trading', label: 'Paper Trading' },
];

export default function TopBar() {
  const [indices, setIndices] = useState<IndicesResponse['indices'] | null>(null);
  const [clock, setClock] = useState(istClock());
  const [open, setOpen] = useState(isMarketOpen());
  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    function load() {
      fetchIndices().then((r) => { if (!cancelled) setIndices(r.indices); }).catch(() => { /* tolerate */ });
    }
    load();
    const t = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setClock(istClock());
      setOpen(isMarketOpen());
    }, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="flex items-center justify-between px-4 py-2.5 border-b border-border1 bg-bg2">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-accent text-lg">⬡</span>
          <span className="font-semibold tracking-wide text-text1">QUANT.AI</span>
          <span className="text-[10px] text-text3 font-mono uppercase">NSE / BSE</span>
        </div>
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map((n) => {
            const active = location.pathname === n.to;
            return (
              <Link key={n.to} to={n.to} className={`tab ${active ? 'active' : ''}`}>{n.label}</Link>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-4">
        <IndexPill data={indices?.nifty} />
        <IndexPill data={indices?.banknifty} />
        <IndexPill data={indices?.vix} />
      </div>

      <div className="flex items-center gap-3">
        <span className={`chip ${open ? 'chip-green' : 'chip-red'}`}>
          <span className="dot" style={{ background: open ? 'var(--green)' : 'var(--red)' }} />
          {open ? 'Market Open' : 'Market Closed'}
        </span>
        <span className="text-[11px] text-text2 font-mono">{clock}</span>
        <button
          onClick={toggleTheme}
          className="btn !p-1.5 !text-base"
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </div>
    </header>
  );
}

function IndexPill({ data }: { data?: IndexLevel }) {
  if (!data) {
    return (
      <div className="flex items-center gap-2 panel-inset rounded px-2 py-1">
        <span className="skeleton w-16 h-3 rounded" />
      </div>
    );
  }
  if (data.error || data.price === undefined) {
    return (
      <div className="flex items-center gap-2 panel-inset rounded px-2 py-1 text-[11px]">
        <span className="text-text3">{data.label}</span>
        <span className="text-text3">—</span>
      </div>
    );
  }
  const c = colorForChange(data.change ?? 0);
  return (
    <div className="flex items-center gap-2 panel-inset rounded px-2 py-1 text-[11px] font-mono">
      <span className="text-text3 uppercase tracking-wider">{data.label}</span>
      <span className="text-text1">{data.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
      <span style={{ color: c }}>{fmtPct(data.change_pct ?? 0)}</span>
    </div>
  );
}
