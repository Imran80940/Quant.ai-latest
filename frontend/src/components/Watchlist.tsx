import { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import { fetchChart, fetchPrice } from '../api/client';
import { fmtINR, fmtPct, colorForChange, emaSparkline } from '../utils';
import type { PriceSnapshot } from '../types';

interface WatchEntry { price: PriceSnapshot | null; spark: number[]; loading: boolean; error?: string }

export default function Watchlist() {
  const watchlist = useStore((s) => s.watchlist);
  const removeFromWatchlist = useStore((s) => s.removeFromWatchlist);
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);
  const activeSymbol = useStore((s) => s.activeSymbol);

  const [entries, setEntries] = useState<Record<string, WatchEntry>>({});

  useEffect(() => {
    let cancelled = false;
    // remove any entries no longer in the list
    setEntries((prev) => {
      const next: Record<string, WatchEntry> = {};
      for (const sym of watchlist) next[sym] = prev[sym] || { price: null, spark: [], loading: true };
      return next;
    });
    // fetch missing data for any new symbols
    for (const sym of watchlist) {
      if (entries[sym]?.price && entries[sym].spark.length) continue;
      Promise.all([
        fetchPrice(sym).catch((e) => ({ __err: true, e })),
        fetchChart(sym, '1mo', '1d').catch(() => ({ bars: [] })),
      ]).then(([priceRes, chartRes]) => {
        if (cancelled) return;
        const errored = (priceRes as { __err?: boolean }).__err;
        const price = !errored ? (priceRes as PriceSnapshot) : null;
        const bars = (chartRes as { bars?: { close: number }[] }).bars || [];
        setEntries((prev) => ({
          ...prev,
          [sym]: { price, spark: bars.map((b) => b.close), loading: false, error: errored ? 'unavailable' : undefined },
        }));
      });
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchlist]);

  return (
    <div className="panel rounded-md flex-1 min-h-0 flex flex-col">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-text2">Watchlist</span>
        <span className="text-[10px] text-text3 font-mono">{watchlist.length}</span>
      </div>

      <div className="flex-1 overflow-auto">
        {watchlist.length === 0 && (
          <div className="p-3 text-xs text-text3 leading-relaxed">
            Empty. Use the <span className="text-accent">+ Watchlist</span> button on a stock header to add it.
          </div>
        )}

        {watchlist.map((sym) => {
          const e = entries[sym];
          const isActive = sym === activeSymbol;
          const sparkPath = e?.spark.length ? emaSparkline(e.spark, 56, 16) : '';
          const sparkColor = e?.price && e.price.change_pct >= 0 ? 'var(--green)' : 'var(--red)';
          return (
            <div
              key={sym}
              role="button"
              tabIndex={0}
              onClick={() => setActiveSymbol(sym)}
              onKeyDown={(ev) => { if (ev.key === 'Enter') setActiveSymbol(sym); }}
              className={`group relative flex items-center justify-between px-3 py-2 border-b border-border1/60 cursor-pointer transition-colors ${
                isActive ? 'bg-bg3' : 'hover:bg-bg3/50'
              }`}
            >
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-mono">{sym.replace('.NS', '')}</span>
                <span className="text-[10px] text-text3 truncate max-w-[110px]">
                  {e?.price?.sector || '—'}
                </span>
              </div>

              <div className="flex items-center gap-2">
                {sparkPath && (
                  <svg width={56} height={16} className="opacity-80">
                    <path d={sparkPath} fill="none" stroke={sparkColor} strokeWidth={1.2} />
                  </svg>
                )}
                <div className="flex flex-col items-end">
                  <span className="text-[12px] text-mono-tight">{e?.price ? fmtINR(e.price.price) : '—'}</span>
                  <span className="text-[10px] text-mono-tight" style={{ color: colorForChange(e?.price?.change ?? null) }}>
                    {e?.price ? fmtPct(e.price.change_pct) : (e?.error ? 'n/a' : '…')}
                  </span>
                </div>
              </div>

              <button
                onClick={(ev) => { ev.stopPropagation(); removeFromWatchlist(sym); }}
                className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 text-text3 hover:text-red1 text-xs px-1"
                title="Remove from watchlist"
              >×</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
