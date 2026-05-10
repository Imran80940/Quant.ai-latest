import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  type AIBacktestAnalysis,
  type BacktestResults,
  type BacktestSummary,
  type DataQualityReport,
  type ICRow,
  type UniverseStats,
  type WFAResult,
  SSE_PROGRESS_URL,
  applyBacktestWeights,
  getActiveBacktest,
  getBacktestAIAnalysis,
  getBacktestDataQuality,
  getBacktestResults,
  getBacktestSummary,
  getUniverseStats,
  resumeBacktest,
  startBacktest,
} from '../api/phase2';
import TopBar from '../components/TopBar';

type Horizon = 1 | 5 | 20;

export default function BacktestPage() {
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ stocks_done: number; stocks_total: number; current_stock: string; percent_complete: number; status: string; total_signals?: number; skipped?: number; max_years_data?: number }>({
    stocks_done: 0, stocks_total: 0, current_stock: '', percent_complete: 0, status: 'idle',
  });
  const [horizon, setHorizon] = useState<Horizon>(5);
  const [error, setError] = useState<string | null>(null);
  const [universeStats, setUniverseStats] = useState<UniverseStats | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQualityReport | null>(null);

  // Initial load
  useEffect(() => {
    refreshAll();
    getUniverseStats().then(setUniverseStats).catch(() => { /* ignore */ });
  }, []);

  // On mount: if a backtest is still in flight (started in a previous
  // tab visit / before a process restart / after laptop wake), reconnect
  // to its progress stream so the user sees the live percentage instead
  // of an idle "Run Full Backtest" button.
  useEffect(() => {
    let cancelled = false;
    let sse: EventSource | null = null;

    (async () => {
      try {
        const info = await getActiveBacktest();
        if (cancelled || !info.active || !info.run) return;

        // If the backend says there are pending/failed stocks, kick off
        // a resume so processing actually proceeds (auto-resume on
        // startup may already have done this — this is idempotent).
        if ((info.run.pending || 0) > 0 || (info.run.failed || 0) > 0) {
          try { await resumeBacktest(info.run.run_id); } catch { /* ignore */ }
        }

        if (cancelled) return;
        setRunning(true);
        if (info.progress) setProgress(info.progress);

        sse = new EventSource(SSE_PROGRESS_URL(info.run.run_id));
        sse.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data);
            setProgress(data);
            if (data.status === 'complete' || data.status === 'failed') {
              sse?.close();
              setRunning(false);
              void refreshAll();
            }
          } catch { /* ignore */ }
        };
        sse.onerror = () => { sse?.close(); };
      } catch { /* ignore — no active run */ }
    })();

    return () => { cancelled = true; sse?.close(); };
  }, []);

  async function refreshAll() {
    setError(null);
    try {
      const s = await getBacktestSummary();
      setSummary(s);
      if (s.has_data) {
        const r = await getBacktestResults();
        setResults(r);
        getBacktestDataQuality().then(setDataQuality).catch(() => { /* ignore */ });
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err?.message || 'Failed to load');
    }
  }

  async function runBacktest() {
    setRunning(true);
    setError(null);
    setProgress({ stocks_done: 0, stocks_total: 0, current_stock: 'starting…', percent_complete: 0, status: 'starting' });
    try {
      const { run_id } = await startBacktest();
      const sse = new EventSource(SSE_PROGRESS_URL(run_id));
      sse.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setProgress(data);
          if (data.status === 'complete' || data.status === 'failed') {
            sse.close();
            setRunning(false);
            void refreshAll();
          }
        } catch {
          // ignore parse errors
        }
      };
      sse.onerror = () => { sse.close(); setRunning(false); };
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err?.message || 'Failed to start backtest');
      setRunning(false);
    }
  }

  return (
    <div className="h-screen flex flex-col bg-bg text-text1 overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-auto p-4 space-y-4">

        {/* ── Run Control Bar ── */}
        <div className="panel rounded-md p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Backtest Lab</h1>
              <p className="text-xs text-text2 mt-0.5">
                Validate Phase 1 scoring against 2 years of historical data — point-in-time, no lookahead.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {summary?.has_data && !running && (
                <span className="text-[11px] text-text3 font-mono">
                  {summary.total_signals?.toLocaleString()} signals · last run {summary.last_run_date?.slice(0, 10)} ({Math.round(summary.duration_seconds || 0)}s)
                </span>
              )}
              <button className="btn btn-primary" onClick={runBacktest} disabled={running}>
                {running ? 'Running…' : summary?.has_data ? 'Rerun Full Backtest' : 'Run Full Backtest'}
              </button>
            </div>
          </div>

          {running && (
            <div className="mt-3">
              <div className="text-[11px] text-text2 mb-1.5 flex justify-between">
                <span>
                  Analyzing <span className="font-mono text-text1">{progress.current_stock}</span>
                  {progress.stocks_total > 0 && ` — ${progress.stocks_done}/${progress.stocks_total}`}
                </span>
                <span className="font-mono">{progress.percent_complete}%</span>
              </div>
              <div className="bar"><span style={{ width: `${progress.percent_complete}%`, background: 'var(--accent)' }} /></div>
            </div>
          )}

          {error && <div className="mt-2 text-xs text-red1">⚠ {error}</div>}

          {/* ── Phase 4: Universe stats strip ── */}
          {universeStats && (
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
              <div className="panel-inset rounded px-2 py-1.5 flex justify-between">
                <span className="text-text3">Universe</span>
                <span className="text-text1">{universeStats.total_active_stocks} stocks</span>
              </div>
              <div className="panel-inset rounded px-2 py-1.5 flex justify-between">
                <span className="text-text3">Sectors</span>
                <span className="text-text1">{universeStats.sectors}</span>
              </div>
              <div className="panel-inset rounded px-2 py-1.5 flex justify-between">
                <span className="text-text3">Cap mix</span>
                <span className="text-text1">L:{universeStats.by_cap.large} M:{universeStats.by_cap.mid} S:{universeStats.by_cap.small}</span>
              </div>
              <div className="panel-inset rounded px-2 py-1.5 flex justify-between" title={universeStats.survivorship_bias_note}>
                <span className="text-text3">Distressed</span>
                <span style={{ color: 'var(--amber)' }}>+{universeStats.distressed_stocks_included}</span>
              </div>
            </div>
          )}
          {running && progress.skipped !== undefined && progress.skipped > 0 && (
            <div className="mt-2 text-[10px] text-text3 font-mono">
              Skipped (no data): {progress.skipped} · Max history seen: {(progress.max_years_data || 0).toFixed(1)}yr · Signals so far: {(progress.total_signals || 0).toLocaleString()}
            </div>
          )}
        </div>

        {/* ── Empty state ── */}
        {!summary?.has_data && !running && (
          <div className="panel rounded-md p-10 text-center">
            <div className="text-text3 text-3xl mb-3">⌛</div>
            <h2 className="text-base font-semibold mb-1">No backtest data yet</h2>
            <p className="text-xs text-text2 max-w-md mx-auto">
              The backtest replays 2 years of daily data for all 100 NSE stocks, computes
              every indicator at every bar (point-in-time, no lookahead), then measures
              whether the Phase 1 score actually predicted forward returns.
              Expect 5-15 minutes on first run; cached afterwards.
            </p>
          </div>
        )}

        {results && summary?.has_data && (
          <>
            {/* ── Hero summary cards ── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <HeroCard
                label="Score ≥ 70 vs Nifty"
                value={results.summary?.score_70_has_edge ? 'EDGE FOUND' : 'NO EDGE'}
                accent={results.summary?.score_70_has_edge ? 'green' : 'red'}
                detail={`Avg 5d: ${results.summary?.score_70_avg_5d_return?.toFixed(2)}%`}
              />
              <HeroCard
                label="Win Rate (Score ≥ 70)"
                value={`${results.summary?.score_70_win_rate?.toFixed(1) ?? '—'}%`}
                accent={(results.summary?.score_70_win_rate ?? 0) > 50 ? 'green' : 'red'}
                detail={`${results.summary?.score_70_count ?? 0} signals`}
              />
              <HeroCard
                label="Best Signal"
                value={results.signal_ic?.indicators?.[0]?.indicator || '—'}
                accent="cyan"
                detail={`IC = ${results.signal_ic?.indicators?.[0]?.ic?.toFixed(3) ?? '—'}`}
              />
              <HeroCard
                label="Signals Analyzed"
                value={(results.summary?.total_signals || 0).toLocaleString()}
                accent="cyan"
                detail={`across ${Object.values(results.strategy_performance?.thresholds || {}).reduce((a, b) => a + (b.unique_stocks || 0), 0) || '?'} stocks`}
              />
            </div>

            {/* ── Phase 3: Walk-Forward Analysis (the honest number) ── */}
            <WalkForwardSection wfa={results.walk_forward_analysis} />

            {/* ── Phase 4: Data Quality + Survivorship caveat ── */}
            <DataQualitySection dq={dataQuality} />

            {/* ── Phase 3: AI as decision engine ── */}
            <AIAnalysisSection />

            {/* ── Score bucket performance ── */}
            <ScoreBucketTable buckets={results.score_buckets?.buckets || []} horizon={horizon} setHorizon={setHorizon} />

            {/* ── Signal IC bar chart ── */}
            <SignalICChart data={results.signal_ic?.indicators || []} />

            {/* ── Weight optimization table ── */}
            <WeightTable data={results.optimal_weights} />

            {/* ── Strategy performance vs Nifty ── */}
            <StrategyPerformance data={results.strategy_performance} />
          </>
        )}
      </div>
    </div>
  );
}

// ── Phase 3: Walk-Forward Analysis section ─────────────────────────────
function WalkForwardSection({ wfa }: { wfa?: WFAResult }) {
  if (!wfa) return null;
  if (wfa.error) {
    return (
      <div className="panel rounded-md p-4">
        <div className="text-xs uppercase tracking-wider text-text2 mb-1">Walk-Forward Validation</div>
        <div className="text-[11px] text-text3">{wfa.error}</div>
      </div>
    );
  }

  const summary = wfa.walk_forward_summary || {};
  const horizons: ('1d' | '5d' | '20d')[] = ['1d', '5d', '20d'];

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between flex-wrap gap-1">
        <div>
          <div className="text-xs uppercase tracking-wider text-text2">Walk-Forward Validation</div>
          <div className="text-[10px] text-text3 mt-0.5">
            Out-of-sample, net of NSE costs. {wfa.window_details?.length ?? 0} OOS windows · 10-day purge gap.
          </div>
        </div>
        <div className="text-[10px] text-text3 font-mono">{wfa.cost_model}</div>
      </div>

      <div className="p-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
        {horizons.map((h) => {
          const d = summary[h];
          if (!d) {
            return (
              <div key={h} className="panel-inset rounded p-3 opacity-50">
                <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">{h.toUpperCase()} horizon</div>
                <div className="text-text3 text-xs">No data</div>
              </div>
            );
          }
          const edgeColor = d.has_edge ? 'var(--green)' : 'var(--red)';
          const bg = d.has_edge ? 'color-mix(in srgb, var(--green) 8%, transparent)' : 'color-mix(in srgb, var(--red) 6%, transparent)';
          const border = d.has_edge ? 'color-mix(in srgb, var(--green) 35%, transparent)' : 'color-mix(in srgb, var(--red) 30%, transparent)';
          return (
            <div key={h} className="rounded p-3" style={{ background: bg, border: `1px solid ${border}` }}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-[10px] uppercase tracking-wider text-text2">{h.toUpperCase()} horizon</div>
                <span className="text-[10px] font-mono" style={{ color: edgeColor }}>
                  {d.has_edge ? 'EDGE' : 'NO EDGE'}
                </span>
              </div>
              <div className="text-2xl font-mono tracking-tight" style={{ color: edgeColor }}>
                {d.avg_net_return_pct >= 0 ? '+' : ''}{d.avg_net_return_pct.toFixed(3)}%
              </div>
              <div className="text-[10px] text-text3 mt-0.5">avg net return per trade</div>
              <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] font-mono">
                <div className="flex justify-between"><span className="text-text3">Win Rate:</span><span>{d.avg_win_rate}%</span></div>
                <div className="flex justify-between"><span className="text-text3">Sharpe:</span><span>{d.avg_sharpe_net.toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="text-text3">Cost/trd:</span><span style={{ color: 'var(--amber)' }}>−{d.avg_transaction_cost_pct.toFixed(3)}%</span></div>
                <div className="flex justify-between"><span className="text-text3">OOS trd:</span><span>{d.total_oos_trades}</span></div>
              </div>
              <div className="text-[10px] text-text3 mt-1.5">
                Gross: {d.avg_gross_return_pct >= 0 ? '+' : ''}{d.avg_gross_return_pct.toFixed(3)}% · {d.n_windows} windows
              </div>
            </div>
          );
        })}
      </div>

      {wfa.methodology && (
        <div className="px-3 py-1.5 text-[10px] text-text3 border-t border-border1 font-mono">
          {wfa.methodology}
        </div>
      )}
    </div>
  );
}

// ── Phase 4: Data Quality + Survivorship Bias caveat ──────────────────
function DataQualitySection({ dq }: { dq: DataQualityReport | null }) {
  if (!dq || !dq.total_stocks_with_data) return null;
  const distData = Object.entries(dq.years_distribution || {})
    .map(([yrs, count]) => ({ years: yrs, count }))
    .sort((a, b) => Number(a.years) - Number(b.years));

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1">
        <div className="text-xs uppercase tracking-wider text-text2">Data Quality Report</div>
        <div className="text-[10px] text-text3 mt-0.5">
          How robust the backtest actually is — a 10-year edge is far stronger than a 2-year one.
        </div>
      </div>

      <div className="p-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
        <div className="panel-inset rounded p-2">
          <div className="text-[9px] text-text3 uppercase tracking-wider">Stocks with data</div>
          <div className="text-lg text-text1">{dq.total_stocks_with_data}</div>
        </div>
        <div className="panel-inset rounded p-2">
          <div className="text-[9px] text-text3 uppercase tracking-wider">Avg years / stock</div>
          <div className="text-lg" style={{ color: dq.avg_years_per_stock >= 5 ? 'var(--green)' : 'var(--amber)' }}>
            {dq.avg_years_per_stock.toFixed(1)}
          </div>
        </div>
        <div className="panel-inset rounded p-2">
          <div className="text-[9px] text-text3 uppercase tracking-wider">5+ years</div>
          <div className="text-lg text-text1">
            {dq.stocks_with_5plus_years}
            <span className="text-text3 text-xs ml-1">
              ({Math.round((dq.stocks_with_5plus_years / dq.total_stocks_with_data) * 100)}%)
            </span>
          </div>
        </div>
        <div className="panel-inset rounded p-2">
          <div className="text-[9px] text-text3 uppercase tracking-wider">8+ years</div>
          <div className="text-lg text-text1">
            {dq.stocks_with_8plus_years}
            <span className="text-text3 text-xs ml-1">
              ({Math.round((dq.stocks_with_8plus_years / dq.total_stocks_with_data) * 100)}%)
            </span>
          </div>
        </div>
      </div>

      {/* Distribution chart */}
      {distData.length > 0 && (
        <div style={{ height: 180 }} className="px-3 pb-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="years" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)"
                     label={{ value: 'years of data', position: 'insideBottom', offset: -2, fill: 'var(--text3)', fontSize: 10 }} />
              <YAxis tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)"
                     label={{ value: 'stocks', angle: -90, position: 'insideLeft', fill: 'var(--text3)', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
              <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Survivorship bias caveat (mandatory per spec) */}
      <div
        className="mx-3 mb-3 rounded p-3 border"
        style={{
          background: 'color-mix(in srgb, var(--amber) 6%, transparent)',
          borderColor: 'color-mix(in srgb, var(--amber) 35%, transparent)',
        }}
      >
        <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--amber)' }}>
          ⚠ Survivorship Bias Caveat
        </div>
        <div className="text-[11px] text-text2 leading-snug">
          Even with the expanded universe (active + 10 distressed/delisted names),
          this dataset still over-represents surviving companies.
          Live performance can be 10-20% worse than backtested numbers.
          <span className="text-text1"> Always paper-trade before risking real capital.</span>
        </div>
      </div>

      {/* Top 10 longest history */}
      {dq.top_20_longest && dq.top_20_longest.length > 0 && (
        <div className="px-3 pb-3">
          <div className="text-[10px] uppercase tracking-wider text-text3 mb-1.5">Top 10 longest history</div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-1 text-[10px] font-mono">
            {dq.top_20_longest.slice(0, 10).map((row) => (
              <div key={row.stock} className="panel-inset rounded px-2 py-1 flex justify-between">
                <span className="text-text2 truncate mr-1">{row.stock.replace('.NS', '')}</span>
                <span className="text-text1">{row.approx_years}yr</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Phase 3: AI Analysis section ───────────────────────────────────────
function AIAnalysisSection() {
  const [analysis, setAnalysis] = useState<AIBacktestAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true); setError(null); setApplied(null);
    try {
      const res = await getBacktestAIAnalysis();
      setAnalysis(res.ai_analysis);
    } catch (e: unknown) {
      const err = e as { message?: string; response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || err?.message || 'AI analysis failed');
    } finally {
      setLoading(false);
    }
  }

  async function apply() {
    if (!analysis?.new_factor_weights) return;
    setApplying(true); setApplied(null);
    try {
      const w = analysis.new_factor_weights;
      await applyBacktestWeights({
        momentum_group:   w.momentum_group,
        trend_group:      w.trend_group,
        volume_group:     w.volume_group,
        volatility_group: w.volatility_group,
      });
      setApplied('✓ Screener now uses backtest-derived weights');
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err?.message || 'Apply failed');
    } finally {
      setApplying(false);
    }
  }

  const verdict = analysis?.verdict;
  const verdictColor = verdict?.system_has_edge ? 'var(--green)' : 'var(--red)';

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="text-xs uppercase tracking-wider text-text2 flex items-center gap-2">
            <span className="text-accent">⬡</span> AI System Analysis
          </div>
          <div className="text-[10px] text-text3 mt-0.5">The AI reads backtest results and proposes concrete weight changes.</div>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={loading}>
          {loading ? 'Analysing…' : analysis ? 'Re-analyse' : 'Analyze Backtest'}
        </button>
      </div>

      {error && <div className="px-3 py-2 text-xs text-red1">⚠ {error}</div>}

      {!analysis && !loading && !error && (
        <div className="p-4 text-xs text-text2 leading-relaxed">
          Click <span className="text-accent">Analyze Backtest</span> to send the WFA, IC, and Ridge results to the AI.
          You'll get a verdict, signals to retire/amplify, and machine-applicable factor weights.
        </div>
      )}

      {loading && (
        <div className="p-4 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-3 w-full rounded" />)}
        </div>
      )}

      {analysis && !loading && (
        <div className="p-3 space-y-3">
          {/* Verdict */}
          {verdict && (
            <div
              className="rounded p-3 border"
              style={{
                background: verdict.system_has_edge ? 'color-mix(in srgb, var(--green) 8%, transparent)' : 'color-mix(in srgb, var(--red) 6%, transparent)',
                borderColor: verdict.system_has_edge ? 'color-mix(in srgb, var(--green) 35%, transparent)' : 'color-mix(in srgb, var(--red) 30%, transparent)',
              }}
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="text-base font-semibold" style={{ color: verdictColor }}>
                  {verdict.system_has_edge ? 'SYSTEM HAS EDGE' : 'NO ROBUST EDGE'}
                </div>
                <span className="chip chip-cyan">Confidence: {verdict.confidence_in_edge}</span>
              </div>
              <div className="mt-2 text-[12px] text-text2 leading-snug">
                <span className="text-green1">→</span> {verdict.primary_evidence}
              </div>
              <div className="mt-1 text-[12px] text-text2 leading-snug">
                <span className="text-amber1">⚠</span> {verdict.biggest_weakness}
              </div>
            </div>
          )}

          {/* Suggested factor weights + apply */}
          {analysis.new_factor_weights && (
            <div className="panel-inset rounded p-3">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <div className="text-[10px] uppercase tracking-wider text-text3">Suggested Factor Weights</div>
                <div className="flex items-center gap-2">
                  {applied && <span className="text-[11px]" style={{ color: 'var(--green)' }}>{applied}</span>}
                  <button className="btn btn-primary" onClick={apply} disabled={applying}>
                    {applying ? 'Applying…' : 'Apply Weights to Screener'}
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px] font-mono">
                {(['momentum_group', 'trend_group', 'volume_group', 'volatility_group'] as const).map((k) => (
                  <div key={k} className="panel rounded p-2">
                    <div className="text-[9px] text-text3 uppercase tracking-wider">{k.replace('_group', '')}</div>
                    <div className="text-lg" style={{ color: 'var(--accent)' }}>
                      {((analysis.new_factor_weights?.[k] || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
              {analysis.new_factor_weights.rationale && (
                <div className="mt-2 text-[11px] text-text2 italic">{analysis.new_factor_weights.rationale}</div>
              )}
            </div>
          )}

          {/* Retire / Amplify */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {analysis.signals_to_retire && analysis.signals_to_retire.length > 0 && (
              <div className="panel-inset rounded p-3">
                <div className="text-[10px] uppercase tracking-wider text-text3 mb-1.5">Retire</div>
                <ul className="space-y-1.5">
                  {analysis.signals_to_retire.map((s, i) => (
                    <li key={i} className="text-[11px]">
                      <span className="chip chip-red mr-2">{s.signal}</span>
                      <span className="text-text2">{s.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {analysis.signals_to_amplify && analysis.signals_to_amplify.length > 0 && (
              <div className="panel-inset rounded p-3">
                <div className="text-[10px] uppercase tracking-wider text-text3 mb-1.5">Amplify</div>
                <ul className="space-y-1.5">
                  {analysis.signals_to_amplify.map((s, i) => (
                    <li key={i} className="text-[11px]">
                      <span className="chip chip-green mr-2">{s.signal} ×{s.new_weight_multiplier?.toFixed(1)}</span>
                      <span className="text-text2">{s.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Operational guidance */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] font-mono">
            {analysis.optimal_score_threshold !== undefined && (
              <div className="panel-inset rounded p-2 flex items-center justify-between">
                <span className="text-text3">Optimal Threshold</span>
                <span className="text-text1">{analysis.optimal_score_threshold}</span>
              </div>
            )}
            {analysis.optimal_holding_period_days !== undefined && (
              <div className="panel-inset rounded p-2 flex items-center justify-between">
                <span className="text-text3">Optimal Hold (days)</span>
                <span className="text-text1">{analysis.optimal_holding_period_days}</span>
              </div>
            )}
            {analysis.position_sizing_rule && (
              <div className="panel-inset rounded p-2 col-span-3 sm:col-span-1">
                <span className="text-text3 text-[10px] uppercase">Position Sizing</span>
                <div className="text-text1 text-[11px] leading-snug mt-0.5">{analysis.position_sizing_rule}</div>
              </div>
            )}
          </div>

          {analysis.new_hypothesis_to_test && (
            <div className="panel-inset rounded p-3">
              <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">Next Hypothesis to Test</div>
              <div className="text-[12px] text-text1 italic leading-snug">"{analysis.new_hypothesis_to_test}"</div>
            </div>
          )}

          <div className="text-right text-[10px] text-text3">
            Based on {analysis._based_on_signals ?? '?'} signals · generated {analysis._generated_at?.slice(11, 19)}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Hero card ──────────────────────────────────────────────────────────
function HeroCard({ label, value, accent, detail }: {
  label: string; value: string | number; accent: 'green' | 'red' | 'amber' | 'cyan';
  detail: string;
}) {
  const color = { green: 'var(--green)', red: 'var(--red)', amber: 'var(--amber)', cyan: 'var(--accent)' }[accent];
  return (
    <div className="panel rounded-md p-3">
      <div className="text-[10px] uppercase tracking-wider text-text3 mb-1.5">{label}</div>
      <div className="text-2xl font-mono tracking-tight" style={{ color }}>{value}</div>
      <div className="text-[11px] text-text2 mt-1 font-mono">{detail}</div>
    </div>
  );
}

// ── Score bucket table ────────────────────────────────────────────────
function ScoreBucketTable({ buckets, horizon, setHorizon }: { buckets: { bucket: string; horizon_days: number; avg_return_pct: number; win_rate: number; sharpe: number; count: number }[]; horizon: Horizon; setHorizon: (h: Horizon) => void }) {
  const filtered = buckets.filter((b) => b.horizon_days === horizon);
  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-text2">Score Bucket Performance</div>
          <div className="text-[10px] text-text3 mt-0.5">Does the score have a monotonic relationship with returns?</div>
        </div>
        <div className="flex gap-1">
          {([1, 5, 20] as Horizon[]).map((h) => (
            <button key={h} className={`tab ${h === horizon ? 'active' : ''}`} onClick={() => setHorizon(h)}>{h}D</button>
          ))}
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-text3 text-[10px] uppercase tracking-wider">
              <th className="text-left  px-3 py-2 font-medium">Score Range</th>
              <th className="text-right px-3 py-2 font-medium">Avg Return</th>
              <th className="text-right px-3 py-2 font-medium">Win Rate</th>
              <th className="text-right px-3 py-2 font-medium">Sharpe</th>
              <th className="text-right px-3 py-2 font-medium">Count</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="text-center text-text3 px-3 py-4 text-xs">No data for this horizon</td></tr>
            )}
            {filtered.map((b) => (
              <tr key={b.bucket} className="border-t border-border1/40 hover:bg-bg3/40">
                <td className="px-3 py-2 text-text1">{b.bucket}</td>
                <td className="px-3 py-2 text-right" style={{ color: b.avg_return_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {b.avg_return_pct >= 0 ? '+' : ''}{b.avg_return_pct.toFixed(3)}%
                </td>
                <td className="px-3 py-2 text-right" style={{ color: b.win_rate >= 50 ? 'var(--green)' : 'var(--red)' }}>{b.win_rate.toFixed(1)}%</td>
                <td className="px-3 py-2 text-right text-text1">{b.sharpe.toFixed(2)}</td>
                <td className="px-3 py-2 text-right text-text2">{b.count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Signal IC bar chart ───────────────────────────────────────────────
function SignalICChart({ data }: { data: ICRow[] }) {
  const colored = useMemo(() => data.map((d) => ({
    ...d,
    color: d.ic_abs > 0.10 ? '#22c55e' : d.ic_abs > 0.05 ? '#f59e0b' : d.ic_abs > 0.02 ? '#a1a1aa' : '#ef4444',
  })), [data]);

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1">
        <div className="text-xs uppercase tracking-wider text-text2">Signal IC (Information Coefficient)</div>
        <div className="text-[10px] text-text3 mt-0.5">Spearman rank correlation with 5-day forward return — IC &gt; 0.05 = meaningful edge</div>
      </div>
      <div style={{ height: Math.max(220, data.length * 32) }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-text3 text-xs">No IC data</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={colored} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="var(--border)" horizontal={false} />
              <XAxis type="number" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
              <YAxis type="category" dataKey="indicator" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" width={140} />
              <Tooltip
                contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                labelStyle={{ color: 'var(--text)' }}
                formatter={((v: unknown, _name: unknown, item: unknown) => {
                  const num = Number(v) || 0;
                  const strength = (item as { payload?: ICRow } | undefined)?.payload?.strength ?? '';
                  return [`${num.toFixed(4)}  (${strength})`, 'IC'];
                }) as never}
              />
              <Bar dataKey="ic" radius={[0, 4, 4, 0]}>
                {colored.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

// ── Weight optimization table ─────────────────────────────────────────
function WeightTable({ data }: { data: BacktestResults['optimal_weights'] }) {
  if (!data || data.error) {
    return (
      <div className="panel rounded-md p-3 text-xs text-text2">
        {data?.error || 'Optimal weights unavailable.'}
      </div>
    );
  }
  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-text2">Weight Optimization (Ridge / TimeSeriesSplit)</div>
          <div className="text-[10px] text-text3 mt-0.5">{data.note} · R² = {data.r2_score?.toFixed(4)} · α = {data.best_alpha}</div>
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-text3 text-[10px] uppercase tracking-wider">
              <th className="text-left  px-3 py-2 font-medium">Indicator</th>
              <th className="text-right px-3 py-2 font-medium">Current</th>
              <th className="text-right px-3 py-2 font-medium">Suggested</th>
              <th className="text-right px-3 py-2 font-medium">Change</th>
              <th className="text-left  px-3 py-2 font-medium">Direction</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {(data.weights || []).map((w) => {
              const big = Math.abs(w.change) > 5;
              const chgColor = w.change_direction === 'increase' ? 'var(--green)' : w.change_direction === 'decrease' ? 'var(--red)' : 'var(--text2)';
              return (
                <tr key={w.indicator} className={`border-t border-border1/40 hover:bg-bg3/40 ${big ? 'border-l-2 border-l-amber1' : ''}`}>
                  <td className="px-3 py-2 text-text1">{w.indicator}</td>
                  <td className="px-3 py-2 text-right text-text2">{w.current_weight.toFixed(1)}</td>
                  <td className="px-3 py-2 text-right text-text1">{w.suggested_weight.toFixed(1)}</td>
                  <td className="px-3 py-2 text-right" style={{ color: chgColor }}>
                    {w.change_direction === 'increase' ? '↑' : w.change_direction === 'decrease' ? '↓' : '·'} {w.change > 0 ? '+' : ''}{w.change.toFixed(1)}
                  </td>
                  <td className="px-3 py-2 text-text2">{w.direction}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Strategy performance vs Nifty ─────────────────────────────────────
function StrategyPerformance({ data }: { data: BacktestResults['strategy_performance'] }) {
  const niftyReturn = data?.nifty_2y_return_pct ?? 0;
  const thresholds = data?.thresholds || {};
  const ths = ['50', '60', '70', '80'];

  // Build merged date series for chart
  const seriesByDate = useMemo(() => {
    const merged: Record<string, Record<string, number>> = {};
    for (const t of ths) {
      const arr = thresholds[t]?.daily_returns;
      if (!arr) continue;
      let cum = 1;
      for (const pt of arr) {
        cum *= 1 + pt.return / 100;
        const d = pt.date.slice(0, 10);
        if (!merged[d]) merged[d] = {};
        merged[d][`s${t}`] = parseFloat(((cum - 1) * 100).toFixed(3));
      }
    }
    return Object.entries(merged)
      .map(([date, vals]) => ({ date, ...vals }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [thresholds]);

  const colorMap: Record<string, string> = { s50: '#a1a1aa', s60: '#f59e0b', s70: '#22d3ee', s80: '#22c55e' };

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1">
        <div className="text-xs uppercase tracking-wider text-text2">Strategy Performance — Score Threshold vs Nifty 50</div>
        <div className="text-[10px] text-text3 mt-0.5">Buy all qualifying signals, hold 5 days; cumulative compound return. Nifty 2Y baseline: <span className="font-mono text-text2">{niftyReturn >= 0 ? '+' : ''}{niftyReturn.toFixed(2)}%</span></div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 p-3 text-[11px] font-mono">
        {ths.map((t) => {
          const r = thresholds[t];
          if (!r || r.error) return (
            <div key={t} className="panel-inset rounded p-2 text-text3">≥{t}: {r?.error || 'no data'}</div>
          );
          return (
            <div key={t} className="panel-inset rounded p-2 space-y-0.5" style={{ borderLeft: `3px solid ${colorMap['s' + t]}` }}>
              <div className="text-[10px] uppercase tracking-wider text-text3">≥ {t}</div>
              <div className="text-text1">{r.cumulative_return_pct >= 0 ? '+' : ''}{r.cumulative_return_pct.toFixed(2)}% cum</div>
              <div className="text-text2">Win {r.win_rate.toFixed(1)}% · Sh {r.sharpe_ratio.toFixed(2)}</div>
              <div style={{ color: r.beats_nifty ? 'var(--green)' : 'var(--red)' }}>
                {r.beats_nifty ? '↑' : '↓'} {r.alpha_vs_nifty >= 0 ? '+' : ''}{r.alpha_vs_nifty.toFixed(2)}% vs Nifty
              </div>
              <div className="text-text3">{r.total_trades} trades · MaxDD {r.max_drawdown_pct.toFixed(1)}%</div>
            </div>
          );
        })}
      </div>

      <div className="px-3 pb-3" style={{ height: 320 }}>
        {seriesByDate.length === 0 ? (
          <div className="h-full flex items-center justify-center text-text3 text-xs">No daily series</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={seriesByDate} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" minTickGap={40} />
              <YAxis tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                labelStyle={{ color: 'var(--text)' }}
                formatter={((v: unknown) => { const n = Number(v) || 0; return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`; }) as never}
              />
              <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono' }} />
              {ths.map((t) => (
                <Line key={t} type="monotone" dataKey={`s${t}`} stroke={colorMap['s' + t]} strokeWidth={t === '70' ? 2 : 1.5} dot={false} name={`Score ≥ ${t}`} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
