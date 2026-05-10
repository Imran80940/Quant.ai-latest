export interface StockMeta {
  symbol: string;
  display_symbol: string;
  name: string;
  sector: string;
}

export interface PriceSnapshot {
  symbol: string;
  display_symbol: string;
  name: string;
  sector: string;
  exchange: string;
  price: number;
  previous_close: number | null;
  change: number;
  change_pct: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  week52_high: number | null;
  week52_low: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  beta: number | null;
  dividend_yield: number | null;
}

export interface OHLCBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Indicators {
  rsi: number;
  macd: number;
  macd_signal: number;
  macd_histogram: number;
  macd_crossover: 'bullish' | 'bearish';
  ema_9: number;
  ema_20: number;
  ema_50: number;
  ema_200: number;
  price_vs_ema9: 'above' | 'below' | 'neutral';
  price_vs_ema20: 'above' | 'below' | 'neutral';
  price_vs_ema50: 'above' | 'below' | 'neutral';
  price_vs_ema200: 'above' | 'below' | 'neutral';
  bb_upper: number;
  bb_middle: number;
  bb_lower: number;
  bb_squeeze: boolean;
  bb_position_pct: number;
  adx: number;
  trend_strength: 'strong' | 'moderate' | 'weak';
  atr: number;
  atr_pct: number;
  obv_trend: 'rising' | 'falling' | 'flat';
  volume_vs_avg20: number;
  stoch_rsi: number;
  supertrend: 'bullish' | 'bearish' | 'neutral';
  vwap: number;
  price_vs_vwap: 'above' | 'below' | 'neutral';
  last_close: number;
}

export type ScreenerMode = 'intraday' | 'shortterm' | 'momentum' | 'breakout' | 'value';

export interface ScreenerCard {
  symbol: string;
  display_symbol: string;
  name: string;
  sector: string;
  price: number;
  change_pct: number;
  score: number;
  grade: string;
  reasons: string[];
  risks: string[];
  indicators: Indicators;
}

export interface ScreenerResponse {
  mode: ScreenerMode;
  generated_at: string;
  scanned: number;
  succeeded: number;
  stocks: ScreenerCard[];
}

export interface IndexLevel {
  label: string;
  symbol: string;
  price?: number;
  change?: number;
  change_pct?: number;
  error?: string;
}

export interface IndicesResponse {
  indices: {
    nifty: IndexLevel;
    banknifty: IndexLevel;
    vix: IndexLevel;
  };
}

export interface AIAnalysis {
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  confidence: number;
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  intraday: {
    entry_low: number;
    entry_high: number;
    target_1: number;
    target_2: number;
    stop_loss: number;
    rr_ratio_t1: number;
    rr_ratio_t2: number;
    exit_by: string;
  };
  shortterm: {
    trigger: string;
    target: number;
    stop_loss: number;
    horizon_days: number;
  };
  key_reasons: string[];
  key_risks: string[];
  signal_summary: {
    trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    momentum: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    volume: 'CONFIRMING' | 'DIVERGING' | 'NEUTRAL';
    volatility: 'LOW' | 'MEDIUM' | 'HIGH';
  };
  one_line: string;
}

export interface AIResponse {
  symbol: string;
  name: string;
  mode: string;
  price_at_analysis: number;
  provider?: 'groq' | 'gemini' | 'claude';
  model: string;
  analysis: AIAnalysis;
}
