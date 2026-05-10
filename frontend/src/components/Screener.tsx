import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store/useStore';
import { runScreener, getRecommendation } from '../api/client';
import { fmtINR, fmtPct, gradeColor, scoreColor } from '../utils';
import type { ScreenerCard, ScreenerMode, ScreenerResponse } from '../types';

const MODES: { id: ScreenerMode; label: string }[] = [
  { id: 'intraday',  label: 'Intraday'   },
  { id: 'shortterm', label: 'Short Term' },
  { id: 'momentum',  label: 'Momentum'   },
  { id: 'breakout',  label: 'Breakout'   },
  { id: 'value',     label: 'Value'      },
];

const AUTO_REFRESH_SEC = 300; // 5 minutes
const SCAN_DURATION_HINT_SEC = 60;

export default function Screener() {
  const mode = useStore((s) => s.screenerMode);
  const setMode = useStore((s) => s.setScreenerMode);
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);
  const setAi = useStore((s) => s.setAi);
  const setAiLoading = useStore((s) => s.setAiLoading);
  const setAiError = useStore((s) => s.setAiError);

  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [progress, setProgress] = useState(0); // 0..1 hint
  const [countdown, setCountdown] = useState(AUTO_REFRESH_SEC);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function scan() {
    setLoading(true); setErr(null); setProgress(0);
    // fake progress bar based on a 60s heuristic
    if (progressRef.current) clearInterval(progressRef.current);
    const start = Date.now();
    progressRef.current = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000;
      setProgress(Math.min(elapsed / SCAN_DURATION_HINT_SEC, 0.95));
    }, 250);
    try {
      const res = await runScreener(mode);
      setData(res);
      setProgress(1);
      setCountdown(AUTO_REFRESH_SEC);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      setErr(err?.response?.data?.detail?.message || err?.message || 'Screener failed');
    } finally {
      if (progressRef.current) { clearInterval(progressRef.current); progressRef.current = null; }
      setLoading(false);
    }
  }

  // Reset data + countdown when mode changes
  useEffect(() => {
    setData(null);
    setErr(null);
    setCountdown(AUTO_REFRESH_SEC);
  }, [mode]);

  // Auto-refresh countdown (only when we have data)
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!data) return;
    intervalRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) { scan(); return AUTO_REFRESH_SEC; }
        return c - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, mode]);

  async function viewChart(card: ScreenerCard) {
    setActiveSymbol(card.symbol);
  }

  async function aiAnalyse(card: ScreenerCard) {
    setActiveSymbol(card.symbol);
    setAiLoading(true);
    setAiError(null);
    try {
      const r = await getRecommendation({
        symbol: card.symbol,
        name: card.name,
        mode,
        indicators: card.indicators,
      });
      setAi(r);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      setAiError(err?.response?.data?.detail?.message || err?.message || 'AI failed');
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="panel rounded-md flex flex-col min-h-0">
      <div className="px-3 py-2 border-b border-border1">
        <div className="text-xs uppercase tracking-wider text-text2 mb-2">Screener</div>
        <div className="flex flex-wrap items-center gap-1">
          {MODES.map((m) => (
            <button key={m.id} className={`tab ${m.id === mode ? 'active' : ''}`} onClick={() => setMode(m.id)}>{m.label}</button>
          ))}
        </div>
      </div>

      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between gap-2">
        <button className="btn btn-primary flex-1" onClick={scan} disabled={loading}>
          {loading ? 'Scanning…' : data ? `Rescan ${MODES.find((m) => m.id === mode)?.label}` : `Scan Market (${mode})`}
        </button>
        {data && !loading && (
          <span className="text-[10px] text-text3 font-mono whitespace-nowrap">↻ {countdown}s</span>
        )}
      </div>

      {loading && (
        <div className="px-3 py-3 border-b border-border1">
          <div className="text-[11px] text-text2 mb-1.5 flex justify-between">
            <span>Scanning 100 stocks across NSE…</span>
            <span className="font-mono">{(progress * 100).toFixed(0)}%</span>
          </div>
          <div className="bar"><span style={{ width: `${progress * 100}%`, background: 'var(--accent)' }} /></div>
        </div>
      )}

      {err && (
        <div className="px-3 py-2 text-xs text-red1 border-b border-border1">⚠ {err}</div>
      )}

      <div className="flex-1 overflow-auto">
        {data && (
          <div className="px-3 py-2 text-[10px] text-text3 font-mono uppercase tracking-wider flex justify-between">
            <span>Top {data.stocks.length} · {mode}</span>
            <span>{data.succeeded}/{data.scanned} scanned</span>
          </div>
        )}

        {data?.stocks.map((card, i) => (
          <ScreenerRow key={card.symbol} card={card} rank={i + 1} onView={() => viewChart(card)} onAi={() => aiAnalyse(card)} />
        ))}

        {!data && !loading && !err && (
          <div className="p-4 text-xs text-text2 leading-relaxed">
            Pick a mode and run <span className="text-accent">Scan Market</span> to rank
            the NSE universe by signal strength. Each stock gets a 0–100 multi-factor
            score with reasons and risks.
          </div>
        )}
      </div>
    </div>
  );
}

function ScreenerRow({ card, rank, onView, onAi }: { card: ScreenerCard; rank: number; onView: () => void; onAi: () => void }) {
  const sc = scoreColor(card.score);
  const gc = gradeColor(card.grade);
  const chgColor = card.change_pct >= 0 ? 'var(--green)' : 'var(--red)';

  return (
    <div className="px-3 py-2.5 border-b border-border1/60 hover:bg-bg3/40 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] text-text3 font-mono w-5">#{rank}</span>
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-mono">{card.display_symbol}</span>
            <span className="text-[10px] text-text3 truncate">{card.sector}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-mono">{fmtINR(card.price)}</div>
          <div className="text-[11px] font-mono" style={{ color: chgColor }}>{fmtPct(card.change_pct)}</div>
        </div>
      </div>

      <div className="mt-1.5 flex items-center gap-2">
        <div className="bar flex-1"><span style={{ width: `${card.score}%`, background: sc }} /></div>
        <span className="text-[11px] font-mono" style={{ color: sc }}>{card.score}</span>
        <span className="chip" style={{ background: `color-mix(in srgb, ${gc} 20%, transparent)`, color: gc }}>{card.grade}</span>
      </div>

      {card.reasons.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] text-text2">
          {card.reasons.slice(0, 3).map((r, i) => (
            <li key={i} className="flex gap-1.5"><span className="text-green1">→</span><span className="truncate">{r}</span></li>
          ))}
        </ul>
      )}
      {card.risks.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-[11px] text-text2">
          {card.risks.slice(0, 2).map((r, i) => (
            <li key={i} className="flex gap-1.5"><span className="text-amber1">⚠</span><span className="truncate">{r}</span></li>
          ))}
        </ul>
      )}

      <div className="mt-2 flex items-center gap-1.5">
        <button className="btn flex-1 text-[10px]" onClick={onView}>View Chart</button>
        <button className="btn btn-primary flex-1 text-[10px]" onClick={onAi}>AI Analysis</button>
      </div>
    </div>
  );
}
