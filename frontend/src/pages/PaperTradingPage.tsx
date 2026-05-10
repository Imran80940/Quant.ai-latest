import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  type LearningInsight,
  type LiveWeights,
  type PaperTrade,
  type PaperTradingAnalytics,
  type PaperTradingStatus,
  SSE_PAPER_STREAM_URL,
  controlEngine,
  getActiveTrades,
  getLearningInsights,
  getLiveWeights,
  getPaperTradingAnalytics,
  getPaperTradingStatus,
  getTrades,
} from '../api/phase2';
import TopBar from '../components/TopBar';

type Tab = 'live' | 'history' | 'insights';

interface LiveEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export default function PaperTradingPage() {
  const [tab, setTab] = useState<Tab>('live');

  return (
    <div className="h-screen flex flex-col bg-bg text-text1 overflow-hidden">
      <TopBar />

      {/* Tab bar */}
      <div className="border-b border-border1 bg-bg2 px-3">
        <div className="flex gap-1 -mb-px">
          {([
            ['live', 'Live'],
            ['history', 'History'],
            ['insights', 'Insights'],
          ] as [Tab, string][]).map(([id, label]) => (
            <button key={id} className={`tab !rounded-none border-b-2 ${tab === id ? '!border-b-accent !text-accent' : '!border-b-transparent'}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3">
        {tab === 'live' && <LiveTab />}
        {tab === 'history' && <HistoryTab />}
        {tab === 'insights' && <InsightsTab />}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 1: LIVE
// ════════════════════════════════════════════════════════════════════════

function LiveTab() {
  const [status, setStatus] = useState<PaperTradingStatus | null>(null);
  const [active, setActive] = useState<PaperTrade[]>([]);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const eventBuffer = useRef<LiveEvent[]>([]);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getPaperTradingStatus();
      setStatus(s);
    } catch { /* ignore */ }
  }, []);

  const loadActive = useCallback(async () => {
    try {
      const r = await getActiveTrades();
      setActive(r.trades);
    } catch { /* ignore */ }
  }, []);

  // Initial load + poll status + active trades every 30s
  useEffect(() => {
    loadStatus();
    loadActive();
    const t = setInterval(() => { loadStatus(); loadActive(); }, 30_000);
    return () => clearInterval(t);
  }, [loadStatus, loadActive]);

  // Subscribe to SSE event stream
  useEffect(() => {
    const sse = new EventSource(SSE_PAPER_STREAM_URL);
    sse.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as LiveEvent;
        if (ev.type === 'heartbeat') return;
        eventBuffer.current = [ev, ...eventBuffer.current].slice(0, 50);
        setEvents([...eventBuffer.current]);

        // Live price update — patch active trades in-place
        if (ev.type === 'price_update') {
          const data = ev.data as { trade_id: string; current_price: number; live_pnl_pct: number };
          setActive((prev) => prev.map((t) => t.trade_id === data.trade_id
            ? { ...t, current_price: data.current_price, live_pnl_pct: data.live_pnl_pct }
            : t));
        }
        // Trade events trigger a refetch of status & active
        if (ev.type === 'trade_opened' || ev.type === 'trade_closed' || ev.type === 'scan_complete') {
          loadStatus();
          loadActive();
        }
      } catch { /* ignore parse errors */ }
    };
    sse.onerror = () => sse.close();
    return () => sse.close();
  }, [loadStatus, loadActive]);

  async function toggleEngine() {
    if (!status) return;
    setBusy(true);
    try {
      await controlEngine(status.engine_running ? 'stop' : 'start');
      await loadStatus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Status bar */}
      <div className="panel rounded-md p-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <span className={`chip ${status?.engine_running ? 'chip-green' : 'chip-neutral'}`}>
            <span className="dot" style={{ background: status?.engine_running ? 'var(--green)' : 'var(--text3)' }} />
            {status?.engine_running ? 'AUTO-ENGINE LIVE' : 'IDLE'}
          </span>
          <span className={`chip ${status?.is_market_open ? 'chip-green' : 'chip-amber'}`}>
            <span className="dot" style={{ background: status?.is_market_open ? 'var(--green)' : 'var(--amber)' }} />
            {status?.is_market_open ? 'Market Open' : 'Market Closed'}
          </span>
          {status?.auto_start && (
            <span className="chip chip-cyan">⚡ Auto-trades intraday</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono">
          <Stat label="Active" value={`${status?.active_trades_count ?? 0} / ${status?.max_concurrent ?? 4}`} />
          <Stat label="Budget" value={`₹${(status?.portfolio_budget_inr ?? 20000).toLocaleString('en-IN')}`} color="var(--accent)" />
          <Stat label="Per Trade" value={`₹${(status?.per_trade_inr ?? 5000).toLocaleString('en-IN')}`} />
          <Stat label="Today" value={`${status?.today_trades ?? 0} trades`} />
          <Stat label="Win Rate" value={`${status?.overall_win_rate?.toFixed(1) ?? '0.0'}%`} />
          <Stat label="Today P&L" value={`${(status?.today_avg_pnl ?? 0) >= 0 ? '+' : ''}${(status?.today_avg_pnl ?? 0).toFixed(2)}%`} color={(status?.today_avg_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
          <Stat label="Conf ≥" value={`${status?.confidence_threshold ?? '—'}`} />
          {status?.last_scan_time && (
            <Stat label="Last Scan" value={new Date(status.last_scan_time).toLocaleTimeString('en-IN', { hour12: false })} />
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] text-text3 font-mono">
            {status?.is_market_open
              ? '● Live · scanning every 30 min'
              : '◌ Will auto-start at 9:15 AM IST'}
          </span>
          {/* Manual override only — engine self-runs */}
          <button className="btn !text-[10px] !py-1" onClick={toggleEngine} disabled={busy} title="Manual override">
            {busy ? '…' : status?.engine_running ? 'pause' : 'resume'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-3">
        {/* Active positions */}
        <div className="panel rounded-md flex flex-col min-h-[400px]">
          <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider text-text2">Active Positions ({active.length})</span>
          </div>
          <div className="flex-1 overflow-auto">
            {active.length === 0 ? (
              <div className="p-6 text-center text-text3 text-xs">
                No active positions.<br />
                {status?.is_market_open
                  ? 'Engine scanning. Auto-opens intraday trades (₹5K each) when AI confidence ≥ threshold.'
                  : 'Market closed. Engine will resume automatically at 9:15 AM IST. Active trades persist.'}
              </div>
            ) : active.map((t) => <ActiveTradeCard key={t.trade_id} t={t} />)}
          </div>
        </div>

        {/* Live event feed */}
        <div className="panel rounded-md flex flex-col min-h-[400px]">
          <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider text-text2">Live Feed</span>
            <span className="text-[10px] text-text3 font-mono">{events.length} events</span>
          </div>
          <div className="flex-1 overflow-auto">
            {events.length === 0 ? (
              <div className="p-4 text-text3 text-xs text-center">
                Waiting for live events. Engine activity (scans, trades, insights) will appear here in real time.
              </div>
            ) : events.map((ev, i) => <LiveEventRow key={i} ev={ev} />)}
          </div>
        </div>
      </div>
    </div>
  );
}

function ActiveTradeCard({ t }: { t: PaperTrade }) {
  const live = t.current_price ?? t.entry_price;
  const livePnl = t.live_pnl_pct ?? 0;
  const profitable = livePnl > 0;
  const nearSL = live <= t.stop_loss * 1.003;
  const cardBorder = nearSL ? 'border-l-red1' : profitable ? 'border-l-green1' : 'border-l-amber1';

  // Progress toward T1: 0% at entry, 100% at T1 (negative = below entry)
  const progress = t.target_1 !== t.entry_price
    ? Math.max(0, Math.min(100, ((live - t.entry_price) / (t.target_1 - t.entry_price)) * 100))
    : 0;

  let reasons: string[] = [];
  try { reasons = JSON.parse(t.ai_reasons || '[]'); } catch { /* ignore */ }

  return (
    <div className={`px-3 py-2.5 border-b border-border1/40 border-l-2 ${cardBorder} hover:bg-bg3/40 transition-colors`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-mono">{t.stock.replace('.NS', '')}</span>
          <span className="chip chip-cyan text-[10px]">{t.trade_type}</span>
          <span className="chip chip-neutral text-[10px] uppercase">{t.horizon}</span>
          <span className="chip chip-amber text-[10px]">Conf {t.ai_confidence}%</span>
        </div>
        <div className="text-right">
          <div className="text-[12px] font-mono">₹{live.toFixed(2)}</div>
          <div className="text-[11px] font-mono" style={{ color: profitable ? 'var(--green)' : 'var(--red)' }}>
            {livePnl >= 0 ? '+' : ''}{livePnl.toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-1 text-[10px] font-mono">
        <span className="text-text3">Entry <span className="text-text1">₹{t.entry_price.toFixed(2)}</span></span>
        <span className="text-text3">T1 <span className="text-green1">₹{t.target_1.toFixed(2)}</span></span>
        <span className="text-text3">SL <span className="text-red1">₹{t.stop_loss.toFixed(2)}</span></span>
      </div>

      <div className="mt-1.5 bar relative">
        <span style={{ width: `${progress}%`, background: profitable ? 'var(--green)' : 'var(--amber)' }} />
      </div>

      {reasons.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] text-text2">
          {reasons.slice(0, 2).map((r, i) => (
            <li key={i} className="flex gap-1.5"><span className="text-green1">→</span><span className="truncate">{r}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LiveEventRow({ ev }: { ev: LiveEvent }) {
  const time = new Date(ev.timestamp).toLocaleTimeString('en-IN', { hour12: false });
  let icon = '·';
  let color = 'var(--text2)';
  let body = '';

  if (ev.type === 'trade_opened') {
    icon = '🟢';
    color = 'var(--green)';
    const d = ev.data as { stock: string; entry: number; confidence: number; mode: string };
    body = `OPENED — ${d.stock?.replace('.NS', '')} LONG @ ₹${d.entry} (${d.confidence}% conf, ${d.mode})`;
  } else if (ev.type === 'trade_closed') {
    icon = '🔴';
    const d = ev.data as { stock: string; result: string; exit_reason: string; pnl_pct: number };
    color = d.result?.startsWith('WIN') ? 'var(--green)' : 'var(--red)';
    body = `CLOSED — ${d.stock?.replace('.NS', '')} ${d.result} (${d.exit_reason}) ${d.pnl_pct >= 0 ? '+' : ''}${d.pnl_pct?.toFixed(2)}%`;
  } else if (ev.type === 'scan_complete') {
    icon = '🔍';
    color = 'var(--accent)';
    const d = ev.data as { candidates_found: number; trades_placed: number };
    body = `SCAN — ${d.candidates_found} candidates, ${d.trades_placed} trades placed`;
  } else if (ev.type === 'scan_started') {
    icon = '🔍';
    color = 'var(--text2)';
    body = 'Scan started…';
  } else if (ev.type === 'insight_generated') {
    icon = '💡';
    color = 'var(--amber)';
    const d = ev.data as { win_rate: number; threshold_change: string };
    body = `INSIGHT — Win ${d.win_rate}%, threshold ${d.threshold_change}`;
  } else if (ev.type === 'engine_started') {
    icon = '🚀';
    color = 'var(--accent)';
    body = 'Engine started';
  } else if (ev.type === 'price_update') {
    return null; // don't clutter the feed with price ticks
  }

  if (!body) return null;
  return (
    <div className="px-3 py-1.5 border-b border-border1/30 text-[11px] font-mono flex gap-2 items-start">
      <span>{icon}</span>
      <span className="text-text3 shrink-0">{time}</span>
      <span style={{ color }}>{body}</span>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 2: HISTORY
// ════════════════════════════════════════════════════════════════════════

function HistoryTab() {
  const [analytics, setAnalytics] = useState<PaperTradingAnalytics | null>(null);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    getPaperTradingAnalytics().then(setAnalytics).catch(() => { /* ignore */ });
    getTrades('all', 50, 0).then((r) => setTrades(r.trades)).catch(() => { /* ignore */ });
  }, []);

  const cumulativeChart = useMemo(() => {
    return (analytics?.cumulative_pnl_series || [])
      .map((p) => ({ date: p.date.slice(0, 10), pnl: p.cum_pnl }))
      .filter((p) => p.date);
  }, [analytics]);

  // Weekly win/loss bucket
  const weeklyChart = useMemo(() => {
    const buckets: Record<string, { wins: number; losses: number }> = {};
    for (const t of trades) {
      if (t.status !== 'CLOSED' || !t.exit_time) continue;
      const week = t.exit_time.slice(0, 10);
      buckets[week] ??= { wins: 0, losses: 0 };
      if (t.result === 'WIN_T1' || t.result === 'WIN_T2') buckets[week].wins++;
      else buckets[week].losses++;
    }
    return Object.entries(buckets)
      .map(([date, v]) => ({ date, wins: v.wins, losses: -v.losses }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [trades]);

  if (!analytics || analytics.total_trades === 0) {
    return (
      <div className="panel rounded-md p-10 text-center">
        <div className="text-text3 text-3xl mb-3">📊</div>
        <h2 className="text-base font-semibold mb-1">No trade history yet</h2>
        <p className="text-xs text-text2 max-w-md mx-auto">
          Once the engine has placed and closed trades, performance metrics, charts, and a full trade log will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard label="Total Trades" value={`${analytics.total_trades}`} />
        <SummaryCard label="Win Rate" value={`${analytics.win_rate?.toFixed(1)}%`} color={(analytics.win_rate ?? 0) >= 50 ? 'var(--green)' : 'var(--red)'} />
        <SummaryCard label="Avg P&L / trade" value={`${(analytics.avg_pnl_per_trade ?? 0) >= 0 ? '+' : ''}${(analytics.avg_pnl_per_trade ?? 0).toFixed(2)}%`} color={(analytics.avg_pnl_per_trade ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
        <SummaryCard label="Total P&L" value={`${(analytics.total_pnl_pct ?? 0) >= 0 ? '+' : ''}${(analytics.total_pnl_pct ?? 0).toFixed(2)}%`} color={(analytics.total_pnl_pct ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="panel rounded-md">
          <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">Cumulative P&L</div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cumulativeChart} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" minTickGap={30} />
                <YAxis tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }} formatter={((v: unknown) => { const n = Number(v) || 0; return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`; }) as never} />
                <ReferenceLine y={0} stroke="var(--border2)" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="pnl" stroke="var(--accent)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel rounded-md">
          <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">Weekly Win / Loss</div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weeklyChart} margin={{ top: 8, right: 12, bottom: 8, left: 0 }} stackOffset="sign">
                <CartesianGrid stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
                <YAxis tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                <ReferenceLine y={0} stroke="var(--border2)" />
                <Bar dataKey="wins" fill="var(--green)" stackId="a" />
                <Bar dataKey="losses" fill="var(--red)" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* By mode */}
      {analytics.by_mode && (
        <div className="panel rounded-md">
          <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">By Mode</div>
          <table className="w-full text-[12px] font-mono">
            <thead>
              <tr className="text-text3 text-[10px] uppercase tracking-wider">
                <th className="text-left  px-3 py-2">Mode</th>
                <th className="text-right px-3 py-2">Trades</th>
                <th className="text-right px-3 py-2">Win Rate</th>
                <th className="text-right px-3 py-2">Avg P&L</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(analytics.by_mode).map(([mode, v]) => (
                <tr key={mode} className="border-t border-border1/40">
                  <td className="px-3 py-2 text-text1 capitalize">{mode}</td>
                  <td className="px-3 py-2 text-right text-text2">{v.trades}</td>
                  <td className="px-3 py-2 text-right" style={{ color: v.win_rate >= 50 ? 'var(--green)' : 'var(--red)' }}>{v.win_rate.toFixed(1)}%</td>
                  <td className="px-3 py-2 text-right" style={{ color: v.avg_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>{v.avg_pnl >= 0 ? '+' : ''}{v.avg_pnl.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Trade log */}
      <div className="panel rounded-md">
        <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">Trade Log</div>
        <div className="overflow-auto">
          <table className="w-full text-[12px] font-mono">
            <thead>
              <tr className="text-text3 text-[10px] uppercase tracking-wider">
                <th className="text-left  px-3 py-2">Date</th>
                <th className="text-left  px-3 py-2">Stock</th>
                <th className="text-right px-3 py-2">Entry</th>
                <th className="text-right px-3 py-2">Exit</th>
                <th className="text-left  px-3 py-2">Result</th>
                <th className="text-right px-3 py-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && (
                <tr><td colSpan={6} className="text-center text-text3 px-3 py-4 text-xs">No trades yet</td></tr>
              )}
              {trades.map((t) => {
                const open = expanded === t.trade_id;
                return (
                  <Fragment key={t.trade_id}>
                    <tr className="border-t border-border1/40 hover:bg-bg3/40 cursor-pointer" onClick={() => setExpanded(open ? null : t.trade_id)}>
                      <td className="px-3 py-2 text-text2">{(t.entry_time || '').slice(0, 16).replace('T', ' ')}</td>
                      <td className="px-3 py-2 text-text1">{t.stock.replace('.NS', '')}</td>
                      <td className="px-3 py-2 text-right">₹{t.entry_price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">{t.exit_price ? `₹${t.exit_price.toFixed(2)}` : '—'}</td>
                      <td className="px-3 py-2"><ResultChip result={t.result} status={t.status} /></td>
                      <td className="px-3 py-2 text-right" style={{ color: (t.pnl_pct ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {t.pnl_pct == null ? '—' : `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%`}
                      </td>
                    </tr>
                    {open && (
                      <tr className="border-t border-border1/40 bg-bg3/20">
                        <td colSpan={6} className="px-3 py-2">
                          <ExpandedTradeRow t={t} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ResultChip({ result, status }: { result: PaperTrade['result']; status: PaperTrade['status'] }) {
  if (status === 'ACTIVE') return <span className="chip chip-cyan">ACTIVE</span>;
  if (result === 'WIN_T1') return <span className="chip chip-green">🟢 WIN T1</span>;
  if (result === 'WIN_T2') return <span className="chip chip-green">🟢 WIN T2</span>;
  if (result === 'LOSS')   return <span className="chip chip-red">🔴 LOSS</span>;
  if (result === 'EXPIRED') return <span className="chip chip-amber">⬜ EXPIRED</span>;
  return <span className="chip chip-neutral">—</span>;
}

function ExpandedTradeRow({ t }: { t: PaperTrade }) {
  let reasons: string[] = [];
  try { reasons = JSON.parse(t.ai_reasons || '[]'); } catch { /* ignore */ }
  let ind: Record<string, unknown> = {};
  try { ind = JSON.parse(t.indicators_at_entry || '{}'); } catch { /* ignore */ }

  return (
    <div className="text-[11px] font-mono space-y-2">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <KV k="Confidence" v={`${t.ai_confidence}%`} />
        <KV k="Conviction" v={t.ai_conviction} />
        <KV k="Score @ Entry" v={t.score_at_entry.toFixed(0)} />
        <KV k="Mode" v={t.horizon} />
        <KV k="Target 1" v={`₹${t.target_1.toFixed(2)}`} color="var(--green)" />
        <KV k="Target 2" v={`₹${t.target_2.toFixed(2)}`} color="var(--green)" />
        <KV k="Stop Loss" v={`₹${t.stop_loss.toFixed(2)}`} color="var(--red)" />
        <KV k="Exit Reason" v={t.exit_reason || '—'} />
      </div>
      {reasons.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">AI Reasons</div>
          <ul className="space-y-0.5 text-text2">
            {reasons.map((r, i) => <li key={i} className="flex gap-1.5"><span className="text-green1">→</span>{r}</li>)}
          </ul>
        </div>
      )}
      {Object.keys(ind).length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">Indicators @ Entry</div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-1 text-text2">
            {(['rsi', 'macd_crossover', 'adx', 'volume_vs_avg20', 'price_vs_vwap', 'price_vs_ema50', 'price_vs_ema200', 'bb_squeeze', 'supertrend', 'atr_pct'] as const).map((k) => (
              <div key={k} className="panel-inset rounded px-1.5 py-1 truncate">
                <span className="text-text3">{k}: </span>
                <span className="text-text1">{String((ind as Record<string, unknown>)[k] ?? '—')}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// TAB 3: INSIGHTS
// ════════════════════════════════════════════════════════════════════════

function InsightsTab() {
  const [data, setData] = useState<{ insights: LearningInsight[]; current_threshold: number } | null>(null);
  const [analytics, setAnalytics] = useState<PaperTradingAnalytics | null>(null);
  const [closedTrades, setClosedTrades] = useState<PaperTrade[]>([]);
  const [weights, setWeights] = useState<LiveWeights | null>(null);

  useEffect(() => {
    getLearningInsights().then(setData).catch(() => { /* ignore */ });
    getPaperTradingAnalytics().then(setAnalytics).catch(() => { /* ignore */ });
    getTrades('CLOSED', 200, 0).then((r) => setClosedTrades(r.trades)).catch(() => { /* ignore */ });
    getLiveWeights().then(setWeights).catch(() => { /* ignore */ });
    // Poll live weights every 60s — they shift when learning fires
    const t = setInterval(() => {
      getLiveWeights().then(setWeights).catch(() => { /* ignore */ });
    }, 60_000);
    return () => clearInterval(t);
  }, []);

  // Phase 3: factor IC from paper trade outcomes
  const factorIC = useMemo(() => {
    if (closedTrades.length < 5) return [];
    const factors = ['momentum', 'trend', 'volume', 'volatility'];
    const buckets: Record<string, number[]> = { momentum: [], trend: [], volume: [], volatility: [] };
    const outcomes: number[] = [];

    for (const t of closedTrades) {
      let ind: Record<string, unknown> = {};
      try { ind = JSON.parse(t.indicators_at_entry || '{}'); } catch { continue; }
      // Inline orthogonal scoring (mirrors backend orthogonalize.py)
      const rsi = Number(ind.rsi) || 50;
      const macdHist = Number(ind.macd_histogram) || 0;
      const stoch = Number(ind.stoch_rsi) || 50;
      const macdCross = ind.macd_crossover === 'bullish' ? 1 : 0;
      const rsiScore = Math.max(0, Math.min(1, (rsi - 30) / 40));
      const macdScore = macdHist ? 1 / (1 + Math.exp(-macdHist * 0.1)) : 0.5;
      const stochScore = Math.max(0, Math.min(1, stoch / 100));
      const momentum = rsiScore * 0.35 + macdScore * 0.30 + stochScore * 0.20 + macdCross * 0.15;

      const emaCount =
        (ind.price_vs_ema9 === 'above' ? 1 : 0) +
        (ind.price_vs_ema20 === 'above' ? 1 : 0) +
        (ind.price_vs_ema50 === 'above' ? 1 : 0) +
        (ind.price_vs_ema200 === 'above' ? 1 : 0);
      const adx = Number(ind.adx) || 0;
      const supertrend = ind.supertrend === 'bullish' ? 1 : 0;
      const vsEma200 = ind.price_vs_ema200 === 'above' ? 1 : 0;
      const adxScore = Math.max(0, Math.min(1, (adx - 15) / 35));
      const trend = (emaCount / 4) * 0.40 + adxScore * 0.25 + supertrend * 0.20 + vsEma200 * 0.15;

      const volRatio = Number(ind.volume_vs_avg20) || 1;
      const obv = ind.obv_trend;
      const vwapAbove = ind.price_vs_vwap === 'above' ? 1 : 0;
      const volScore = Math.max(0, Math.min(1, (volRatio - 0.5) / 2));
      const obvScore = obv === 'rising' ? 1 : obv === 'falling' ? 0 : 0.5;
      const volume = volScore * 0.50 + obvScore * 0.30 + vwapAbove * 0.20;

      const bbSqueeze = ind.bb_squeeze ? 1 : 0;
      const atrPct = Number(ind.atr_pct) || 2;
      const bbPos = (Number(ind.bb_position_pct) || 50) / 100;
      const atrScore = Math.max(0, Math.min(1, 1 - (atrPct - 0.5) / 5));
      const volatility = bbSqueeze * 0.45 + atrScore * 0.35 + bbPos * 0.20;

      buckets.momentum.push(momentum);
      buckets.trend.push(trend);
      buckets.volume.push(volume);
      buckets.volatility.push(volatility);
      outcomes.push(t.result === 'WIN_T1' || t.result === 'WIN_T2' ? 1 : 0);
    }

    if (outcomes.length < 5) return [];

    // Pearson correlation as proxy for IC (close enough for 4 buckets, 5+ samples)
    const pearson = (x: number[], y: number[]) => {
      const n = x.length;
      const mx = x.reduce((a, b) => a + b, 0) / n;
      const my = y.reduce((a, b) => a + b, 0) / n;
      let num = 0, dx2 = 0, dy2 = 0;
      for (let i = 0; i < n; i++) { const a = x[i] - mx, b = y[i] - my; num += a * b; dx2 += a * a; dy2 += b * b; }
      const den = Math.sqrt(dx2 * dy2);
      return den > 0 ? num / den : 0;
    };

    return factors.map((f) => ({ factor: f, ic: pearson(buckets[f], outcomes) }));
  }, [closedTrades]);

  const thresholdSeries = useMemo(() => {
    if (!data) return [];
    return [...data.insights]
      .reverse()
      .map((i) => ({ date: i.insight_date.slice(0, 10), threshold: i.threshold_after }));
  }, [data]);

  // Indicator avg-in-wins vs avg-in-losses summary
  const signalEdge = useMemo(() => {
    if (closedTrades.length === 0) return [];
    const keys = ['rsi', 'adx', 'volume_vs_avg20', 'atr_pct', 'stoch_rsi'];
    const winSums: Record<string, number> = {};
    const winCounts: Record<string, number> = {};
    const lossSums: Record<string, number> = {};
    const lossCounts: Record<string, number> = {};
    for (const t of closedTrades) {
      let ind: Record<string, unknown> = {};
      try { ind = JSON.parse(t.indicators_at_entry || '{}'); } catch { /* ignore */ }
      const isWin = t.result === 'WIN_T1' || t.result === 'WIN_T2';
      for (const k of keys) {
        const v = Number(ind[k]);
        if (!Number.isFinite(v)) continue;
        if (isWin) { winSums[k] = (winSums[k] || 0) + v; winCounts[k] = (winCounts[k] || 0) + 1; }
        else       { lossSums[k] = (lossSums[k] || 0) + v; lossCounts[k] = (lossCounts[k] || 0) + 1; }
      }
    }
    return keys.map((k) => {
      const aw = winCounts[k] ? winSums[k] / winCounts[k] : null;
      const al = lossCounts[k] ? lossSums[k] / lossCounts[k] : null;
      const dir = aw !== null && al !== null ? (aw > al ? 'higher in wins' : aw < al ? 'lower in wins' : 'no edge') : 'insufficient';
      return {
        indicator: k,
        avg_in_wins: aw,
        avg_in_losses: al,
        edge_direction: dir,
      };
    });
  }, [closedTrades]);

  return (
    <div className="space-y-3">

      {/* ── Phase 3: Live Factor Weights (visible proof the system is learning) ── */}
      <LiveWeightsPanel weights={weights} />

      {/* ── Phase 3: Factor IC from paper trades ── */}
      {factorIC.length > 0 && <FactorICChart data={factorIC} />}

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
        <div className="panel rounded-md p-4">
          <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">Current Confidence Threshold</div>
          <div className="text-5xl font-mono tracking-tight text-accent">{data?.current_threshold ?? '—'}</div>
          <div className="text-[11px] text-text2 mt-2">
            Self-tuned every 10 closed trades. Higher = pickier, lower = more aggressive.
          </div>
        </div>

        <div className="panel rounded-md p-3">
          <div className="text-xs uppercase tracking-wider text-text2 mb-2">Threshold Over Time</div>
          <div style={{ height: 140 }}>
            {thresholdSeries.length === 0 ? (
              <div className="h-full flex items-center justify-center text-text3 text-xs">No insights logged yet</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={thresholdSeries}>
                  <CartesianGrid stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
                  <YAxis tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" domain={[55, 80]} />
                  <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <Line type="stepAfter" dataKey="threshold" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Insights feed */}
      <div className="panel rounded-md">
        <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">Learning Insights</div>
        {(data?.insights || []).length === 0 ? (
          <div className="p-6 text-center text-text3 text-xs">
            No insights yet. The engine generates a new pattern analysis every 10 closed trades.
          </div>
        ) : (
          <div className="divide-y divide-border1/30">
            {(data?.insights || []).map((ins) => (
              <div key={ins.id} className="px-3 py-3">
                <div className="flex items-center justify-between gap-2 text-[11px] font-mono mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="chip chip-amber">Insight #{ins.id}</span>
                    <span className="text-text3">{ins.insight_date}</span>
                  </div>
                  <div className="text-text2">
                    Trades: <span className="text-text1">{ins.trades_analyzed}</span> · Win <span className={ins.win_rate >= 0.5 ? 'text-green1' : 'text-red1'}>{(ins.win_rate * 100).toFixed(0)}%</span> · Avg <span className={ins.avg_pnl >= 0 ? 'text-green1' : 'text-red1'}>{ins.avg_pnl >= 0 ? '+' : ''}{ins.avg_pnl.toFixed(2)}%</span>
                  </div>
                </div>
                <div className="text-[12px] text-text2 leading-relaxed">{ins.ai_insight}</div>
                <div className="text-[10px] text-text3 mt-1 font-mono">
                  Threshold: {ins.threshold_before} → {ins.threshold_after}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Signal edge table */}
      <div className="panel rounded-md">
        <div className="px-3 py-2 border-b border-border1 text-xs uppercase tracking-wider text-text2">Signal Edge — Wins vs Losses</div>
        {signalEdge.length === 0 || closedTrades.length === 0 ? (
          <div className="p-4 text-center text-text3 text-xs">Not enough closed trades yet to compute signal edge.</div>
        ) : (
          <table className="w-full text-[12px] font-mono">
            <thead>
              <tr className="text-text3 text-[10px] uppercase tracking-wider">
                <th className="text-left  px-3 py-2">Indicator</th>
                <th className="text-right px-3 py-2">Avg in Wins</th>
                <th className="text-right px-3 py-2">Avg in Losses</th>
                <th className="text-left  px-3 py-2">Edge</th>
              </tr>
            </thead>
            <tbody>
              {signalEdge.map((s) => (
                <tr key={s.indicator} className="border-t border-border1/40">
                  <td className="px-3 py-2 text-text1">{s.indicator}</td>
                  <td className="px-3 py-2 text-right text-green1">{s.avg_in_wins == null ? '—' : s.avg_in_wins.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right text-red1">{s.avg_in_losses == null ? '—' : s.avg_in_losses.toFixed(2)}</td>
                  <td className="px-3 py-2 text-text2">{s.edge_direction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {analytics?.current_streak ? (
        <div className="panel rounded-md p-3 text-[12px] font-mono flex items-center justify-between">
          <span className="text-text2">Current streak</span>
          <span style={{ color: analytics.streak_type === 'win' ? 'var(--green)' : 'var(--red)' }}>
            {analytics.current_streak} {analytics.streak_type === 'win' ? 'wins' : 'losses'} in a row
          </span>
        </div>
      ) : null}
    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────
function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-text3">{label}:</span>
      <span style={{ color: color || 'var(--text)' }}>{value}</span>
    </span>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="panel rounded-md p-3">
      <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">{label}</div>
      <div className="text-2xl font-mono tracking-tight" style={{ color: color || 'var(--text)' }}>{value}</div>
    </div>
  );
}

function KV({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div className="panel-inset rounded px-2 py-1 flex items-center justify-between">
      <span className="text-text3">{k}</span>
      <span style={{ color: color || 'var(--text)' }}>{v}</span>
    </div>
  );
}

// ── Phase 3: Live factor weights panel ─────────────────────────────────
function LiveWeightsPanel({ weights }: { weights: LiveWeights | null }) {
  if (!weights) {
    return (
      <div className="panel rounded-md p-4">
        <div className="text-xs uppercase tracking-wider text-text2 mb-1">Live Factor Weights</div>
        <div className="skeleton h-12 w-full rounded mt-2" />
      </div>
    );
  }
  const factors: { key: keyof LiveWeights; label: string; color: string }[] = [
    { key: 'momentum',   label: 'Momentum',   color: 'var(--accent)' },
    { key: 'trend',      label: 'Trend',      color: 'var(--purple)' },
    { key: 'volume',     label: 'Volume',     color: 'var(--green)'  },
    { key: 'volatility', label: 'Volatility', color: 'var(--amber)'  },
  ];
  const learned = weights.source === 'paper_trade_learning';

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="text-xs uppercase tracking-wider text-text2">Live Factor Weights</div>
          <div className="text-[10px] text-text3 mt-0.5">
            Driving the screener AND paper trading right now. Updates every 10 closed trades.
          </div>
        </div>
        <span className={`chip ${learned ? 'chip-green' : 'chip-neutral'}`}>
          {learned ? '● Self-tuned from paper trades' : '○ Default weights'}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3">
        {factors.map((f) => {
          const pct = Number(weights[f.key]) * 100;
          return (
            <div key={f.key} className="panel-inset rounded p-3">
              <div className="text-[10px] uppercase tracking-wider text-text3">{f.label}</div>
              <div className="text-2xl font-mono tracking-tight mt-0.5" style={{ color: f.color }}>
                {pct.toFixed(1)}<span className="text-text3 text-base">%</span>
              </div>
              <div className="bar mt-2"><span style={{ width: `${pct.toFixed(1)}%`, background: f.color, transition: 'width 600ms ease' }} /></div>
            </div>
          );
        })}
      </div>
      <div className="px-3 py-1.5 text-[10px] text-text3 border-t border-border1 flex justify-between flex-wrap gap-1">
        <span>Sum: {(weights.sum * 100).toFixed(1)}% · Threshold: {weights.confidence_threshold}</span>
        <span>Last updated: {weights.last_updated === 'never' ? '—' : weights.last_updated.slice(0, 19).replace('T', ' ')}</span>
      </div>
    </div>
  );
}

// ── Phase 3: Factor IC chart from paper trade outcomes ─────────────────
function FactorICChart({ data }: { data: { factor: string; ic: number }[] }) {
  const sorted = [...data].sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic));
  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1">
        <div className="text-xs uppercase tracking-wider text-text2">Which Factor Predicted Your Wins?</div>
        <div className="text-[10px] text-text3 mt-0.5">
          Pearson correlation between each orthogonal factor and actual win/loss outcomes.
          IC &gt; 0.05 = meaningful edge. Computed from {data.length > 0 ? 'closed paper trades' : 'no data'}.
        </div>
      </div>
      <div style={{ height: 220 }} className="p-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sorted} layout="vertical" margin={{ top: 6, right: 18, left: 50, bottom: 6 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis type="number" domain={[-0.3, 0.3]} tick={{ fill: 'var(--text2)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
            <YAxis dataKey="factor" type="category" tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'JetBrains Mono' }} stroke="var(--border2)" />
            <Tooltip
              contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border2)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
              formatter={(v) => [Number(v).toFixed(4), 'IC']}
            />
            <ReferenceLine x={0} stroke="var(--text3)" />
            <ReferenceLine x={0.05} stroke="var(--green)" strokeDasharray="3 3" />
            <ReferenceLine x={-0.05} stroke="var(--red)" strokeDasharray="3 3" />
            <Bar dataKey="ic" radius={[0, 3, 3, 0]}>
              {sorted.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.ic > 0.05 ? 'var(--green)' : d.ic > 0.01 ? 'var(--amber)' : d.ic < -0.01 ? 'var(--red)' : 'var(--text3)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
