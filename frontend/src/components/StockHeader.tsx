import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { fetchPrice } from '../api/client';
import { fmtINR, fmtPct, fmtChange, fmtCompact, isMarketOpen, colorForChange } from '../utils';

export default function StockHeader() {
  const symbol = useStore((s) => s.activeSymbol);
  const price = useStore((s) => s.price);
  const setPrice = useStore((s) => s.setPrice);
  const addToWatchlist = useStore((s) => s.addToWatchlist);
  const watchlist = useStore((s) => s.watchlist);

  // Initial fetch on symbol change
  useEffect(() => {
    let cancelled = false;
    setPrice(null);
    fetchPrice(symbol)
      .then((p) => { if (!cancelled) setPrice(p); })
      .catch(() => { /* StockHeader leaves price null and shows skeleton */ });
    return () => { cancelled = true; };
  }, [symbol, setPrice]);

  // Live polling (15s) during market hours
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    function tick() {
      if (!isMarketOpen()) return;
      fetchPrice(symbol).then(setPrice).catch(() => { /* silent */ });
    }
    timer = setInterval(tick, 15_000);
    return () => { if (timer) clearInterval(timer); };
  }, [symbol, setPrice]);

  if (!price) {
    return (
      <div className="panel rounded-md p-4">
        <div className="skeleton h-5 w-40 rounded mb-3" />
        <div className="skeleton h-8 w-32 rounded" />
      </div>
    );
  }

  const inWatchlist = watchlist.includes(symbol);
  const chgColor = colorForChange(price.change);

  return (
    <div className="panel rounded-md p-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">{price.display_symbol}</span>
            <span className="chip chip-neutral">{price.exchange}</span>
            <span className="chip chip-cyan">{price.sector}</span>
          </div>
          <div className="text-xs text-text2 truncate">{price.name}</div>
        </div>

        <div className="flex flex-col items-end">
          <div className="text-2xl font-mono tracking-tight">{fmtINR(price.price)}</div>
          <div className="flex items-center gap-2 mt-0.5 font-mono text-sm" style={{ color: chgColor }}>
            <span>{fmtChange(price.change)}</span>
            <span>{fmtPct(price.change_pct)}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-mono-tight">
        <Stat label="OPEN"   value={fmtINR(price.open)} />
        <Stat label="HIGH"   value={fmtINR(price.high)} />
        <Stat label="LOW"    value={fmtINR(price.low)} />
        <Stat label="VOL"    value={fmtCompact(price.volume)} />
        <Stat label="52W H"  value={fmtINR(price.week52_high)} />
        <Stat label="52W L"  value={fmtINR(price.week52_low)} />
        <Stat label="MKT CAP" value={fmtCompact(price.market_cap)} />
        <Stat label="P/E"    value={price.pe_ratio !== null ? price.pe_ratio.toFixed(2) : '—'} />
      </div>

      <div className="mt-3 flex justify-end">
        <button
          className={`btn ${inWatchlist ? '' : 'btn-primary'}`}
          onClick={() => !inWatchlist && addToWatchlist(symbol)}
          disabled={inWatchlist}
        >
          {inWatchlist ? '✓ In Watchlist' : '+ Watchlist'}
        </button>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-inset rounded px-2 py-1.5 flex items-center justify-between">
      <span className="text-text3">{label}</span>
      <span className="text-text1">{value}</span>
    </div>
  );
}
