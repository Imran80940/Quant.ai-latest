import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../store/useStore';
import type { StockMeta } from '../types';

export default function SearchBar() {
  const universe = useStore((s) => s.universe);
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);

  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim().toLowerCase()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const results = useMemo<StockMeta[]>(() => {
    if (!debounced) return [];
    return universe
      .filter((s) =>
        s.display_symbol.toLowerCase().includes(debounced) ||
        s.symbol.toLowerCase().includes(debounced) ||
        s.name.toLowerCase().includes(debounced)
      )
      .slice(0, 12);
  }, [debounced, universe]);

  // Reset highlight when results change
  useEffect(() => { setHighlight(0); }, [results]);

  // Close on outside click
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  function pick(s: StockMeta) {
    setActiveSymbol(s.symbol);
    setQuery('');
    setDebounced('');
    setOpen(false);
    inputRef.current?.blur();
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || !results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => (h + 1) % results.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => (h - 1 + results.length) % results.length); }
    else if (e.key === 'Enter')   { e.preventDefault(); pick(results[highlight]); }
    else if (e.key === 'Escape')  { setOpen(false); }
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex items-center gap-2 panel rounded-md px-3 py-2">
        <span className="text-text3 text-sm">⌕</span>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          placeholder="Search 100 stocks (RELIANCE, TCS…)"
          className="bg-transparent flex-1 outline-none text-sm text-text1 placeholder:text-text3 font-mono"
        />
        {query && (
          <button onClick={() => { setQuery(''); setDebounced(''); }} className="text-text3 hover:text-text1 text-xs">×</button>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 mt-1 panel rounded-md shadow-2xl z-30 max-h-80 overflow-auto">
          {results.map((r, i) => (
            <button
              key={r.symbol}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => { e.preventDefault(); pick(r); }}
              className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors ${
                i === highlight ? 'bg-bg3' : 'hover:bg-bg3'
              }`}
            >
              <div className="flex flex-col">
                <span className="text-sm text-text1 font-mono">{r.display_symbol}</span>
                <span className="text-[11px] text-text3 truncate max-w-[180px]">{r.name}</span>
              </div>
              <span className="chip chip-neutral">{r.sector}</span>
            </button>
          ))}
        </div>
      )}

      {open && debounced && results.length === 0 && (
        <div className="absolute left-0 right-0 mt-1 panel rounded-md p-3 text-text3 text-xs z-30">
          No matches in NSE universe.
        </div>
      )}
    </div>
  );
}
