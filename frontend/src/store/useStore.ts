import { create } from 'zustand';
import type { AIResponse, Indicators, PriceSnapshot, ScreenerMode, StockMeta } from '../types';

const WATCHLIST_KEY = 'quantai.watchlist.v1';
const ACTIVE_KEY = 'quantai.activeSymbol.v1';
const THEME_KEY = 'quantai.theme.v1';

export type Theme = 'dark' | 'light';

function loadTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === 'light' ? 'light' : 'dark';
  } catch { return 'dark'; }
}
function persistTheme(t: Theme) {
  try { localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ }
}
function applyTheme(t: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', t);
  }
}

function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((s) => typeof s === 'string') : [];
  } catch {
    return [];
  }
}

function persistWatchlist(items: string[]) {
  try { localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items)); } catch { /* ignore */ }
}

function loadActive(): string {
  try { return localStorage.getItem(ACTIVE_KEY) || 'RELIANCE.NS'; } catch { return 'RELIANCE.NS'; }
}
function persistActive(sym: string) {
  try { localStorage.setItem(ACTIVE_KEY, sym); } catch { /* ignore */ }
}

export type Timeframe = '1D' | '5D' | '1M' | '3M' | '6M' | '1Y';
export type ChartType = 'candle' | 'line' | 'area';

interface AppState {
  universe: StockMeta[];
  setUniverse: (u: StockMeta[]) => void;

  activeSymbol: string;
  setActiveSymbol: (s: string) => void;

  price: PriceSnapshot | null;
  setPrice: (p: PriceSnapshot | null) => void;

  indicators: Indicators | null;
  setIndicators: (i: Indicators | null) => void;

  ai: AIResponse | null;
  aiLoading: boolean;
  aiError: string | null;
  setAi: (r: AIResponse | null) => void;
  setAiLoading: (b: boolean) => void;
  setAiError: (e: string | null) => void;

  timeframe: Timeframe;
  setTimeframe: (t: Timeframe) => void;

  chartType: ChartType;
  setChartType: (t: ChartType) => void;

  emaToggles: { ema9: boolean; ema20: boolean; ema50: boolean; ema200: boolean };
  toggleEma: (k: 'ema9' | 'ema20' | 'ema50' | 'ema200') => void;

  screenerMode: ScreenerMode;
  setScreenerMode: (m: ScreenerMode) => void;

  watchlist: string[];
  addToWatchlist: (s: string) => void;
  removeFromWatchlist: (s: string) => void;

  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

export const useStore = create<AppState>((set, get) => ({
  universe: [],
  setUniverse: (u) => set({ universe: u }),

  activeSymbol: loadActive(),
  setActiveSymbol: (s) => { persistActive(s); set({ activeSymbol: s, ai: null, aiError: null }); },

  price: null,
  setPrice: (p) => set({ price: p }),

  indicators: null,
  setIndicators: (i) => set({ indicators: i }),

  ai: null,
  aiLoading: false,
  aiError: null,
  setAi: (r) => set({ ai: r }),
  setAiLoading: (b) => set({ aiLoading: b }),
  setAiError: (e) => set({ aiError: e }),

  timeframe: '6M',
  setTimeframe: (t) => set({ timeframe: t }),

  chartType: 'candle',
  setChartType: (t) => set({ chartType: t }),

  emaToggles: { ema9: false, ema20: true, ema50: true, ema200: true },
  toggleEma: (k) => set({ emaToggles: { ...get().emaToggles, [k]: !get().emaToggles[k] } }),

  screenerMode: 'intraday',
  setScreenerMode: (m) => set({ screenerMode: m }),

  watchlist: loadWatchlist(),
  addToWatchlist: (s) => {
    const cur = get().watchlist;
    if (cur.includes(s)) return;
    const next = [...cur, s];
    persistWatchlist(next);
    set({ watchlist: next });
  },
  removeFromWatchlist: (s) => {
    const next = get().watchlist.filter((x) => x !== s);
    persistWatchlist(next);
    set({ watchlist: next });
  },

  theme: (() => { const t = loadTheme(); applyTheme(t); return t; })(),
  toggleTheme: () => {
    const next: Theme = get().theme === 'dark' ? 'light' : 'dark';
    persistTheme(next);
    applyTheme(next);
    set({ theme: next });
  },
  setTheme: (t) => {
    persistTheme(t);
    applyTheme(t);
    set({ theme: t });
  },
}));

export const TIMEFRAME_PARAMS: Record<Timeframe, { range: string; interval: string }> = {
  '1D': { range: '1d',  interval: '5m' },
  '5D': { range: '5d',  interval: '15m' },
  '1M': { range: '1mo', interval: '1d' },
  '3M': { range: '3mo', interval: '1d' },
  '6M': { range: '6mo', interval: '1d' },
  '1Y': { range: '1y',  interval: '1wk' },
};
