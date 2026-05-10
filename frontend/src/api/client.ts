import axios from 'axios';
import type {
  AIResponse,
  IndicesResponse,
  Indicators,
  OHLCBar,
  PriceSnapshot,
  ScreenerMode,
  ScreenerResponse,
  StockMeta,
} from '../types';

const BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000';

const http = axios.create({
  baseURL: BASE,
  timeout: 90_000,
  headers: { 'Content-Type': 'application/json' },
});

export async function fetchUniverse(): Promise<{ count: number; stocks: StockMeta[] }> {
  const { data } = await http.get('/api/universe');
  return data;
}

export async function fetchPrice(symbol: string): Promise<PriceSnapshot> {
  const { data } = await http.get(`/api/price/${encodeURIComponent(symbol)}`);
  return data;
}

export async function fetchChart(
  symbol: string,
  range: string,
  interval: string
): Promise<{ symbol: string; range: string; interval: string; bars: OHLCBar[] }> {
  const { data } = await http.get(`/api/chart/${encodeURIComponent(symbol)}`, {
    params: { range, interval },
  });
  return data;
}

export async function fetchIndicators(symbol: string): Promise<{ symbol: string; indicators: Indicators }> {
  const { data } = await http.get(`/api/indicators/${encodeURIComponent(symbol)}`);
  return data;
}

export async function runScreener(mode: ScreenerMode, top = 10): Promise<ScreenerResponse> {
  const { data } = await http.get('/api/screener', { params: { mode, top } });
  return data;
}

export async function fetchIndices(): Promise<IndicesResponse> {
  const { data } = await http.get('/api/indices');
  return data;
}

export async function getRecommendation(payload: {
  symbol: string;
  name?: string;
  mode: ScreenerMode;
  indicators?: Indicators;
  price_data?: PriceSnapshot;
}): Promise<AIResponse> {
  const { data } = await http.post('/api/recommend', payload);
  return data;
}
