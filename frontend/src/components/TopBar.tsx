import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchIndices } from '../api/client';
import { useStore } from '../store/useStore';
import type { IndexLevel, IndicesResponse } from '../types';
import { fmtPct, isMarketOpen, istClock, colorForChange } from '../utils';

const NAV_LINKS: { to: string; label: string }[] = [
  { to: '/',              label: 'Terminal' },
  { to: '/backtest',      label: 'Backtest' },
  { to: '/paper-trading', label: 'Paper' },
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
      fetchIndices().then((r) => { if (!cancelled) setIndices(r.indices); }).catch(() => {});
    }
    load();
    const t = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  useEffect(() => {
    const t = setInterval(() => { setClock(istClock()); setOpen(isMarketOpen()); }, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="border-b border-border1 bg-bg2">
      {/* Top row: logo | nav | controls */}
      <div className="flex items-center gap-2 px-3 py-2">
        {/* Logo */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-accent">⬡</span>
          <span className="font-semibold text-text1 text-sm">QUANT.AI</span>
        </div>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 overflow-x-auto flex-1 mx-1">
          {NAV_LINKS.map((n) => {
            const active = location.pathname === n.to;
            return (
              <Link key={n.to} to={n.to}
                className={`tab whitespace-nowrap !px-2 !py-1 !text-[11px] ${active ? 'active' : ''}`}>
                {n.label}
              </Link>
            );
          })}
        </nav>

        {/* Market status + theme toggle */}
        <div className="flex items-center gap-2 shrink-0">
          <span className={`chip !text-[10px] ${open ? 'chip-green' : 'chip-red'}`}>
            <span className="dot" style={{ background: open ? 'var(--green)' : 'var(--red)' }} />
            <span className="hidden sm:inline">{open ? 'Market Open' : 'Market Closed'}</span>
            <span className="sm:hidden">{open ? 'Open' : 'Closed'}</span>
          </span>
          <span className="hidden lg:inline text-[11px] text-text2 font-mono">{clock}</span>
          <button onClick={toggleTheme} className="btn !p-1.5 !text-sm" aria-label="Toggle theme">
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
      </div>

      {/* Index pills — horizontal scroll on mobile */}
      <div className="flex items-center gap-2 px-3 pb-2 overflow-x-auto">
        <IndexPill data={indices?.nifty} />
        <IndexPill data={indices?.banknifty} />
        <IndexPill data={indices?.vix} />
      </div>
    </header>
  );
}

function IndexPill({ data }: { data?: IndexLevel }) {
  if (!data) {
    return (
      <div className="flex items-center gap-1 panel-inset rounded px-2 py-1 shrink-0">
        <span className="skeleton w-14 h-3 rounded" />
      </div>
    );
  }
  if (data.error || data.price === undefined) {
    return (
      <div className="flex items-center gap-1 panel-inset rounded px-2 py-1 text-[10px] shrink-0">
        <span className="text-text3">{data.label}</span>
        <span className="text-text3">—</span>
      </div>
    );
  }
  const c = colorForChange(data.change ?? 0);
  return (
    <div className="flex items-center gap-1.5 panel-inset rounded px-2 py-1 text-[10px] font-mono shrink-0">
      <span className="text-text3 uppercase tracking-wider">{data.label}</span>
      <span className="text-text1">{data.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
      <span style={{ color: c }}>{fmtPct(data.change_pct ?? 0)}</span>
    </div>
  );
}
