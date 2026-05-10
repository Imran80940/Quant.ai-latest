import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
  createChart,
} from 'lightweight-charts';
import { TIMEFRAME_PARAMS, useStore, type Timeframe, type ChartType } from '../store/useStore';
import { fetchChart } from '../api/client';
import type { OHLCBar } from '../types';
import { fmtINR, fmtCompact } from '../utils';

const TIMEFRAMES: Timeframe[] = ['1D', '5D', '1M', '3M', '6M', '1Y'];
const CHART_TYPES: { id: ChartType; label: string }[] = [
  { id: 'candle', label: 'Candle' },
  { id: 'line',   label: 'Line' },
  { id: 'area',   label: 'Area' },
];

const EMA_COLORS = {
  ema9:   { color: '#f59e0b', width: 1   },
  ema20:  { color: '#a855f7', width: 1   },
  ema50:  { color: '#22d3ee', width: 1.5 },
  ema200: { color: '#ef4444', width: 2   },
} as const;

function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let sum = 0;
  for (let i = 0; i < period; i++) sum += values[i];
  let prev = sum / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    const v = values[i] * k + prev * (1 - k);
    out[i] = v;
    prev = v;
  }
  return out;
}

function lineDataFromEma(bars: OHLCBar[], values: (number | null)[]): LineData[] {
  const out: LineData[] = [];
  for (let i = 0; i < bars.length; i++) {
    const v = values[i];
    if (v === null || Number.isNaN(v)) continue;
    out.push({ time: bars[i].time as UTCTimestamp, value: v });
  }
  return out;
}

interface OHLCRowState { o?: number; h?: number; l?: number; c?: number; v?: number; chg?: number }

export default function Chart() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceSeriesRef = useRef<ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaSeriesRefs = useRef<Partial<Record<keyof typeof EMA_COLORS, ISeriesApi<'Line'>>>>({});

  const symbol = useStore((s) => s.activeSymbol);
  const timeframe = useStore((s) => s.timeframe);
  const setTimeframe = useStore((s) => s.setTimeframe);
  const chartType = useStore((s) => s.chartType);
  const setChartType = useStore((s) => s.setChartType);
  const emaToggles = useStore((s) => s.emaToggles);
  const toggleEma = useStore((s) => s.toggleEma);
  const theme = useStore((s) => s.theme);

  const [bars, setBars] = useState<OHLCBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<OHLCRowState>({});

  // Build chart once
  useEffect(() => {
    if (!containerRef.current) return;
    const cs = getComputedStyle(document.documentElement);
    const chartBg   = cs.getPropertyValue('--chart-bg').trim()   || '#09090b';
    const chartGrid = cs.getPropertyValue('--chart-grid').trim() || '#1c1c20';
    const chartText = cs.getPropertyValue('--chart-text').trim() || '#a1a1aa';
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      layout: { background: { color: chartBg }, textColor: chartText, fontFamily: 'JetBrains Mono' },
      grid:   { vertLines: { color: chartGrid }, horzLines: { color: chartGrid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: chartGrid, scaleMargins: { top: 0.08, bottom: 0.28 } },
      timeScale: { borderColor: chartGrid, timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    // volume in lower pane via separate price scale
    const vol = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: '#22c55e33',
    });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    volSeriesRef.current = vol;

    const onResize = () => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(containerRef.current);

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData || param.seriesData.size === 0) {
        setHover({}); return;
      }
      const ps = priceSeriesRef.current;
      if (!ps) return;
      const data = param.seriesData.get(ps);
      if (!data) { setHover({}); return; }
      const v = volSeriesRef.current ? param.seriesData.get(volSeriesRef.current) as { value?: number } | undefined : undefined;
      const anyData = data as { open?: number; high?: number; low?: number; close?: number; value?: number };
      const close = anyData.close ?? anyData.value;
      const open = anyData.open ?? close;
      const chg = open && close ? ((close - open) / open) * 100 : 0;
      setHover({
        o: anyData.open, h: anyData.high, l: anyData.low,
        c: close, v: v?.value, chg,
      });
    });

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      priceSeriesRef.current = null;
      volSeriesRef.current = null;
      emaSeriesRefs.current = {};
    };
  }, []);

  // Re-style chart when theme changes (no need to recreate it)
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // Wait one tick so the CSS variable update is committed
    requestAnimationFrame(() => {
      const cs = getComputedStyle(document.documentElement);
      const chartBg   = cs.getPropertyValue('--chart-bg').trim()   || '#09090b';
      const chartGrid = cs.getPropertyValue('--chart-grid').trim() || '#1c1c20';
      const chartText = cs.getPropertyValue('--chart-text').trim() || '#a1a1aa';
      chart.applyOptions({
        layout: { background: { color: chartBg }, textColor: chartText },
        grid:   { vertLines: { color: chartGrid }, horzLines: { color: chartGrid } },
        rightPriceScale: { borderColor: chartGrid },
        timeScale: { borderColor: chartGrid },
      });
    });
  }, [theme]);

  // Recreate price series when chart type changes
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (priceSeriesRef.current) {
      try { chart.removeSeries(priceSeriesRef.current); } catch { /* ignore */ }
      priceSeriesRef.current = null;
    }
    if (chartType === 'candle') {
      priceSeriesRef.current = chart.addCandlestickSeries({
        upColor: '#22c55e', downColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      });
    } else if (chartType === 'line') {
      priceSeriesRef.current = chart.addLineSeries({ color: '#22d3ee', lineWidth: 2 });
    } else {
      priceSeriesRef.current = chart.addAreaSeries({
        lineColor: '#22d3ee', topColor: 'rgba(34,211,238,0.32)', bottomColor: 'rgba(34,211,238,0.02)', lineWidth: 2,
      });
    }
    // re-feed bars if we have them
    if (bars.length && priceSeriesRef.current) {
      setSeriesData(priceSeriesRef.current, chartType, bars);
    }
  }, [chartType, bars]);

  // Manage EMA series visibility
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    (Object.keys(EMA_COLORS) as Array<keyof typeof EMA_COLORS>).forEach((k) => {
      const want = emaToggles[k];
      const existing = emaSeriesRefs.current[k];
      if (want && !existing) {
        const s = chart.addLineSeries({ color: EMA_COLORS[k].color, lineWidth: EMA_COLORS[k].width as 1 | 2 | 3 | 4, priceLineVisible: false, lastValueVisible: false });
        emaSeriesRefs.current[k] = s;
        if (bars.length) {
          const period = parseInt(k.replace('ema', ''), 10);
          const closes = bars.map((b) => b.close);
          s.setData(lineDataFromEma(bars, ema(closes, period)));
        }
      } else if (!want && existing) {
        try { chart.removeSeries(existing); } catch { /* ignore */ }
        delete emaSeriesRefs.current[k];
      }
    });
  }, [emaToggles, bars]);

  // Load chart bars
  useEffect(() => {
    let cancelled = false;
    const { range, interval } = TIMEFRAME_PARAMS[timeframe];
    setLoading(true); setErr(null);
    fetchChart(symbol, range, interval)
      .then((res) => {
        if (cancelled) return;
        setBars(res.bars);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e?.response?.data?.detail?.message || e?.message || 'Chart data unavailable';
        setErr(typeof msg === 'string' ? msg : 'Chart data unavailable');
        setBars([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, timeframe]);

  // Push bars into series
  useEffect(() => {
    const ps = priceSeriesRef.current;
    if (!ps || !bars.length) return;
    setSeriesData(ps, chartType, bars);
    if (volSeriesRef.current) {
      volSeriesRef.current.setData(
        bars.map((b) => ({
          time: b.time as UTCTimestamp,
          value: b.volume,
          color: b.close >= b.open ? '#22c55e55' : '#ef444455',
        }))
      );
    }
    // refresh EMAs to match new bars
    (Object.keys(EMA_COLORS) as Array<keyof typeof EMA_COLORS>).forEach((k) => {
      const s = emaSeriesRefs.current[k];
      if (!s) return;
      const period = parseInt(k.replace('ema', ''), 10);
      s.setData(lineDataFromEma(bars, ema(bars.map((b) => b.close), period)));
    });
    chartRef.current?.timeScale().fitContent();
  }, [bars, chartType]);

  const last = bars[bars.length - 1];
  const display = useMemo<OHLCRowState>(() => {
    if (Object.keys(hover).length) return hover;
    if (!last) return {};
    const prev = bars[bars.length - 2];
    const chg = prev ? ((last.close - prev.close) / prev.close) * 100 : 0;
    return { o: last.open, h: last.high, l: last.low, c: last.close, v: last.volume, chg };
  }, [hover, last, bars]);

  return (
    <div className="flex flex-col h-full panel rounded-md overflow-hidden">
      {/* Tabs row */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border1">
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map((tf) => (
            <button key={tf} className={`tab ${tf === timeframe ? 'active' : ''}`} onClick={() => setTimeframe(tf)}>{tf}</button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {CHART_TYPES.map((ct) => (
            <button key={ct.id} className={`tab ${ct.id === chartType ? 'active' : ''}`} onClick={() => setChartType(ct.id)}>{ct.label}</button>
          ))}
        </div>
      </div>

      {/* EMA toggles */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-border1 text-xs text-text2">
        {(['ema9', 'ema20', 'ema50', 'ema200'] as const).map((k) => (
          <label key={k} className="flex items-center gap-1.5 cursor-pointer select-none hover:text-text1 transition-colors">
            <input type="checkbox" checked={emaToggles[k]} onChange={() => toggleEma(k)} className="accent-accent" />
            <span className="dot" style={{ background: EMA_COLORS[k].color }} />
            <span className="font-mono uppercase">{k.replace('ema', 'EMA')}</span>
          </label>
        ))}
      </div>

      {/* Chart canvas */}
      <div className="relative flex-1 min-h-0">
        {loading && <div className="absolute inset-0 flex items-center justify-center text-text2 text-xs z-10">Loading chart…</div>}
        {err && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-text2 text-xs z-10">
            <span className="text-red1">⚠ {err}</span>
            <button className="btn" onClick={() => setTimeframe(timeframe)}>Retry</button>
          </div>
        )}
        <div ref={containerRef} className="absolute inset-0" />
      </div>

      {/* OHLCV bar */}
      <div className="px-3 py-2 border-t border-border1 text-[11px] text-mono-tight flex flex-wrap items-center gap-x-4 gap-y-1">
        <Stat label="O" value={display.o !== undefined ? fmtINR(display.o) : '—'} />
        <Stat label="H" value={display.h !== undefined ? fmtINR(display.h) : '—'} />
        <Stat label="L" value={display.l !== undefined ? fmtINR(display.l) : '—'} />
        <Stat label="C" value={display.c !== undefined ? fmtINR(display.c) : '—'} />
        <Stat label="V" value={display.v !== undefined ? fmtCompact(display.v) : '—'} />
        <span className="text-text3">|</span>
        <span style={{ color: (display.chg ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
          Chg: {display.chg !== undefined ? `${display.chg >= 0 ? '+' : ''}${display.chg.toFixed(2)}%` : '—'}
        </span>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-text3">{label}:</span>
      <span className="text-text1">{value}</span>
    </span>
  );
}

function setSeriesData(series: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'>, type: ChartType, bars: OHLCBar[]) {
  if (type === 'candle') {
    (series as ISeriesApi<'Candlestick'>).setData(
      bars.map((b) => ({
        time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close,
      }))
    );
  } else {
    (series as ISeriesApi<'Line'> | ISeriesApi<'Area'>).setData(
      bars.map((b) => ({ time: b.time as UTCTimestamp, value: b.close }))
    );
  }
}
