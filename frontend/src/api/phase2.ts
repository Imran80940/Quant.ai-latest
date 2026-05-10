/** Phase 2 API client — backtesting + paper trading.
 *  Lives alongside the existing /api/client.ts so Phase 1 stays untouched.
 */
import axios from 'axios';

const BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000';
const http = axios.create({ baseURL: BASE, timeout: 90_000, headers: { 'Content-Type': 'application/json' } });

// ── Backtest types ────────────────────────────────────────────────────
export interface BacktestSummary {
  has_data: boolean;
  message?: string;
  total_signals?: number;
  last_run_date?: string;
  duration_seconds?: number;
  score_70_avg_5d_return?: number;
  score_70_win_rate?: number;
  score_70_count?: number;
  score_70_has_edge?: boolean;
}

export interface BucketRow {
  bucket: string;
  horizon_days: number;
  avg_return_pct: number;
  win_rate: number;
  sharpe: number;
  count: number;
}

export interface ICRow {
  indicator: string;
  ic: number;
  ic_abs: number;
  p_value: number;
  significant: boolean;
  strength: 'Strong Alpha' | 'Meaningful Alpha' | 'Weak Alpha' | 'No Edge';
  n_observations: number;
}

export interface WeightRow {
  indicator: string;
  current_weight: number;
  suggested_weight: number;
  raw_coefficient: number;
  direction: 'positive' | 'negative';
  change: number;
  change_direction: 'increase' | 'decrease' | 'maintain';
}

export interface PerfThreshold {
  threshold: number;
  total_trades: number;
  unique_stocks: number;
  avg_return_pct: number;
  win_rate: number;
  sharpe_ratio: number;
  cumulative_return_pct: number;
  max_drawdown_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  beats_nifty: boolean;
  alpha_vs_nifty: number;
  daily_returns: { date: string; return: number }[];
  error?: string;
}

export interface BacktestResults {
  summary: BacktestSummary;
  score_buckets: { buckets?: BucketRow[]; error?: string };
  signal_ic: { indicators?: ICRow[]; error?: string };
  optimal_weights: { weights?: WeightRow[]; r2_score?: number; best_alpha?: number; note?: string; error?: string };
  strategy_performance: {
    thresholds?: Record<string, PerfThreshold>;
    nifty_2y_return_pct?: number;
    benchmark?: string;
    error?: string;
  };
  // ── Phase 3 additions ─────────────────────────────────────────────
  walk_forward_analysis?: WFAResult;
  strategy_performance_all_horizons?: PerfAllHorizons;
  weight_recommendations?: WeightRecommendations;
}

// ── Phase 3 types ─────────────────────────────────────────────────────

export interface WFAHorizonSummary {
  avg_net_return_pct: number;
  avg_gross_return_pct: number;
  avg_transaction_cost_pct: number;
  avg_win_rate: number;
  avg_sharpe_net: number;
  total_oos_trades: number;
  n_windows: number;
  has_edge: boolean;
}

export interface WFAResult {
  walk_forward_summary?: Partial<Record<'1d' | '5d' | '20d', WFAHorizonSummary>>;
  window_details?: { period: string; optimal_threshold: number; train_sharpe: number }[];
  oos_period_results?: {
    window_start: string; window_end: string; horizon_days: number;
    threshold_used: number; avg_net_return_pct: number; avg_gross_return_pct: number;
    transaction_cost_pct: number; win_rate: number; sharpe_net: number; n_trades: number;
  }[];
  methodology?: string;
  cost_model?: string;
  error?: string;
}

export interface PerfHorizonRow {
  threshold: number;
  horizon_days: number;
  n_trades: number;
  avg_gross_return_pct: number;
  avg_net_return_pct: number;
  transaction_cost_pct: number;
  win_rate_pct: number;
  sharpe_ratio_net: number;
  cumulative_net_pct: number;
  max_drawdown_pct: number;
  nifty_avg_return_pct: number;
  alpha_vs_nifty: number;
  beats_nifty: boolean;
  has_real_edge: boolean;
}

export interface PerfAllHorizons {
  by_horizon?: Partial<Record<'1d' | '5d' | '20d', Record<string, PerfHorizonRow>>>;
  nifty_benchmarks?: Record<string, number>;
  cost_model?: Record<string, number>;
  slippage_model?: Record<string, number>;
  error?: string;
}

export interface WeightRecommendations {
  available: boolean;
  recommendations?: {
    indicator: string; action: 'INCREASE' | 'DECREASE'; from: number; to: number; ic: number; reason: string;
  }[];
  new_weights_for_screener?: Record<string, number>;
  apply_instruction?: string;
}

export interface AIBacktestAnalysis {
  verdict?: {
    system_has_edge: boolean;
    confidence_in_edge: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';
    primary_evidence: string;
    biggest_weakness: string;
  };
  new_factor_weights?: {
    momentum_group: number; trend_group: number; volume_group: number; volatility_group: number;
    rationale: string;
  };
  signals_to_retire?: { signal: string; reason: string }[];
  signals_to_amplify?: { signal: string; new_weight_multiplier: number; reason: string }[];
  regime_adjustments?: Record<string, { momentum_weight_boost: number; volume_weight_boost: number }>;
  optimal_score_threshold?: number;
  optimal_holding_period_days?: number;
  new_hypothesis_to_test?: string;
  position_sizing_rule?: string;
  _generated_at?: string;
  _based_on_signals?: number;
  error?: string;
}

export interface AIBacktestResponse {
  backtest_summary?: BacktestSummary;
  ai_analysis: AIBacktestAnalysis;
  generated_at: string;
}

export interface MarketRegime {
  regime: 'BULL_TRENDING' | 'BULL_VOLATILE' | 'SIDEWAYS' | 'BEAR_VOLATILE' | 'BEAR_CRISIS';
  regime_label: string;
  regime_color: string;
  score_multiplier: number;
  intraday_ok: boolean;
  regime_note: string;
  signal_adjustments: string[];
  nifty_price?: number;
  nifty_vs_ema50: string;
  nifty_vs_ema200: string;
  nifty_trend_20d: string;
  india_vix?: number;
  vix_level: string;
  timestamp: string;
}

export interface LiveWeights {
  momentum: number;
  trend: number;
  volume: number;
  volatility: number;
  sum: number;
  confidence_threshold: number;
  source: 'paper_trade_learning' | 'default';
  last_updated: string;
}

export async function startBacktest(): Promise<{ run_id: string; status: string; stocks_total: number; estimated_minutes: number }> {
  const { data } = await http.post('/api/backtest/run');
  return data;
}

export async function getBacktestSummary(): Promise<BacktestSummary> {
  const { data } = await http.get('/api/backtest/summary');
  return data;
}

export interface ActiveBacktestInfo {
  active: boolean;
  run?: {
    run_id: string;
    completed: number; pending: number; failed: number; running: number;
    total: number; last_activity?: string;
  };
  progress?: {
    status: string; stocks_done: number; stocks_total: number;
    current_stock: string; percent_complete: number;
    total_signals?: number; skipped?: number; max_years_data?: number;
  };
}

export async function getActiveBacktest(): Promise<ActiveBacktestInfo> {
  const { data } = await http.get('/api/backtest/active');
  return data;
}

export async function resumeBacktest(runId: string): Promise<{ status: string; run_id: string; pending?: number; completed?: number }> {
  const { data } = await http.post(`/api/backtest/resume/${runId}`);
  return data;
}

export async function getBacktestResults(): Promise<BacktestResults> {
  const { data } = await http.get('/api/backtest/results');
  return data;
}

// ── Paper trading types ───────────────────────────────────────────────
export interface PaperTrade {
  trade_id: string;
  stock: string;
  trade_type: string;
  entry_price: number;
  entry_time: string;
  target_1: number;
  target_2: number;
  stop_loss: number;
  horizon: string;
  ai_bias: string;
  ai_confidence: number;
  ai_conviction: string;
  ai_reasons: string;
  score_at_entry: number;
  indicators_at_entry: string;
  status: 'ACTIVE' | 'CLOSED';
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  result: 'WIN_T1' | 'WIN_T2' | 'LOSS' | 'EXPIRED' | null;
  pnl_pct: number | null;
  created_date: string;
  sector?: string;
  name?: string;
  current_price?: number;
  live_pnl_pct?: number;
}

export interface PaperTradingStatus {
  engine_status: string;
  engine_running: boolean;
  is_market_open: boolean;
  active_trades_count: number;
  active_trades: PaperTrade[];
  confidence_threshold: number;
  last_scan_time: string | null;
  next_scan_in_minutes: number;
  total_trades_all_time: number;
  total_wins: number;
  overall_win_rate: number;
  today_trades: number;
  today_avg_pnl: number;
  // Phase 4 budget fields
  portfolio_budget_inr?: number;
  per_trade_inr?: number;
  max_concurrent?: number;
  trade_horizon?: string;
  auto_start?: boolean;
}

export interface PaperTradingAnalytics {
  total_trades: number;
  win_rate?: number;
  total_pnl_pct?: number;
  avg_pnl_per_trade?: number;
  by_mode?: Record<string, { trades: number; win_rate: number; avg_pnl: number }>;
  best_trade?: { stock: string; pnl: number };
  worst_trade?: { stock: string; pnl: number };
  current_streak?: number;
  streak_type?: string;
  cumulative_pnl_series?: { date: string; cum_pnl: number; stock: string }[];
  message?: string;
}

export interface LearningInsight {
  id: number;
  insight_date: string;
  trades_analyzed: number;
  win_rate: number;
  avg_pnl: number;
  confidence_ic: number;
  ai_insight: string;
  threshold_before: number;
  threshold_after: number;
}

export async function getPaperTradingStatus(): Promise<PaperTradingStatus> {
  const { data } = await http.get('/api/paper-trading/status');
  return data;
}

export async function getActiveTrades(): Promise<{ trades: PaperTrade[] }> {
  const { data } = await http.get('/api/paper-trading/active');
  return data;
}

export async function getTrades(status: 'all' | 'ACTIVE' | 'CLOSED' = 'all', limit = 50, offset = 0): Promise<{ trades: PaperTrade[] }> {
  const { data } = await http.get('/api/paper-trading/trades', { params: { status, limit, offset } });
  return data;
}

export async function getPaperTradingAnalytics(): Promise<PaperTradingAnalytics> {
  const { data } = await http.get('/api/paper-trading/analytics');
  return data;
}

export async function getLearningInsights(): Promise<{ insights: LearningInsight[]; current_threshold: number }> {
  const { data } = await http.get('/api/paper-trading/insights');
  return data;
}

export async function controlEngine(action: 'start' | 'stop' | 'reset_threshold'): Promise<{ status: string }> {
  const { data } = await http.post('/api/paper-trading/control', { action });
  return data;
}

export const SSE_PROGRESS_URL = (runId: string) => `${BASE}/api/backtest/progress/${runId}`;
export const SSE_PAPER_STREAM_URL = `${BASE}/api/paper-trading/stream`;

// ── Phase 4 types ─────────────────────────────────────────────────────

export interface UniverseStats {
  total_active_stocks: number;
  total_backtest_stocks: number;
  distressed_stocks_included: number;
  sectors: number;
  by_sector: Record<string, number>;
  by_cap: { large: number; mid: number; small: number };
  survivorship_bias_note: string;
}

export interface DataQualityRow {
  stock: string;
  signal_count: number;
  earliest_date: string;
  latest_date: string;
  approx_years: number;
}

export interface DataQualityReport {
  total_stocks_with_data: number;
  avg_years_per_stock: number;
  max_years: number;
  min_years: number;
  years_distribution: Record<string, number>;
  stocks_with_5plus_years: number;
  stocks_with_8plus_years: number;
  top_20_longest: DataQualityRow[];
  bottom_20_shortest: DataQualityRow[];
  message?: string;
}

export async function getUniverseStats(): Promise<UniverseStats> {
  const { data } = await http.get('/api/universe/stats');
  return data;
}

export async function getBacktestDataQuality(): Promise<DataQualityReport> {
  const { data } = await http.get('/api/backtest/data-quality');
  return data;
}

// ── Phase 3 endpoints ─────────────────────────────────────────────────

export async function getMarketRegime(): Promise<MarketRegime> {
  const { data } = await http.get('/api/regime');
  return data;
}

export async function getLiveWeights(): Promise<LiveWeights> {
  const { data } = await http.get('/api/paper-trading/live-weights');
  return data;
}

export async function getBacktestAIAnalysis(): Promise<AIBacktestResponse> {
  const { data } = await http.get('/api/backtest/ai-analysis');
  return data;
}

export async function applyBacktestWeights(
  newWeights: Record<string, number>
): Promise<{ status: string; weights: { factor: string; weight: number }[]; message: string }> {
  const { data } = await http.post('/api/backtest/apply-weights', { new_weights_for_screener: newWeights });
  return data;
}

export async function getBacktestWalkForward(): Promise<WFAResult> {
  const { data } = await http.get('/api/backtest/walk-forward');
  return data;
}
