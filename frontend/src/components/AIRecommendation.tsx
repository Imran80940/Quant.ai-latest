import { useStore } from '../store/useStore';
import { getRecommendation } from '../api/client';
import { fmtINR } from '../utils';

function biasStyle(bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL'): string {
  if (bias === 'BULLISH') return 'var(--green)';
  if (bias === 'BEARISH') return 'var(--red)';
  return 'var(--amber)';
}

function dot(state: string): string {
  const s = state.toUpperCase();
  if (s === 'BULLISH' || s === 'CONFIRMING' || s === 'LOW') return 'var(--green)';
  if (s === 'BEARISH' || s === 'DIVERGING' || s === 'HIGH') return 'var(--red)';
  return 'var(--amber)';
}

export default function AIRecommendation() {
  const symbol = useStore((s) => s.activeSymbol);
  const indicators = useStore((s) => s.indicators);
  const price = useStore((s) => s.price);
  const screenerMode = useStore((s) => s.screenerMode);
  const ai = useStore((s) => s.ai);
  const aiLoading = useStore((s) => s.aiLoading);
  const aiError = useStore((s) => s.aiError);
  const setAi = useStore((s) => s.setAi);
  const setAiLoading = useStore((s) => s.setAiLoading);
  const setAiError = useStore((s) => s.setAiError);

  async function run() {
    setAiLoading(true);
    setAiError(null);
    try {
      const r = await getRecommendation({
        symbol,
        name: price?.name || '',
        mode: screenerMode,
        indicators: indicators || undefined,
        price_data: price || undefined,
      });
      setAi(r);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: { message?: string; error?: string } } }; message?: string };
      const detail = err?.response?.data?.detail;
      const msg = detail?.message || detail?.error || err?.message || 'AI analysis failed';
      setAiError(msg);
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-accent text-sm">⬡</span>
          <span className="text-xs uppercase tracking-wider text-text2">
            {ai?.provider === 'claude' ? 'Claude'
              : ai?.provider === 'gemini' ? 'Gemini'
              : 'Groq'} Analysis
          </span>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={aiLoading || !indicators || !price}>
          {aiLoading ? 'Analysing…' : ai ? 'Regenerate' : 'Get AI Analysis'}
        </button>
      </div>

      {!ai && !aiLoading && !aiError && (
        <div className="p-4 text-xs text-text2 leading-relaxed">
          Click <span className="text-accent">Get AI Analysis</span> to send the current
          indicator pack to Claude. You'll get a structured trade plan with entry zones,
          targets, stop loss, R:R ratios, and short-term outlook.
        </div>
      )}

      {aiLoading && (
        <div className="p-3 space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton h-3 w-full rounded" />
          ))}
        </div>
      )}

      {aiError && !aiLoading && (
        <div className="p-3 text-xs text-red1 leading-relaxed">
          ⚠ {aiError}<br />
          <span className="text-text3">AI analysis temporarily unavailable. Technical signals still shown.</span>
        </div>
      )}

      {ai && !aiLoading && (
        <div className="p-3 space-y-3">
          {/* Bias + confidence */}
          <div>
            <div className="flex items-center justify-between">
              <span className="text-base font-semibold tracking-wide" style={{ color: biasStyle(ai.analysis.bias) }}>
                {ai.analysis.bias}
              </span>
              <span className="text-[11px] text-text2 font-mono">Conf: {ai.analysis.confidence}%</span>
            </div>
            <div className="bar mt-1.5">
              <span style={{ width: `${ai.analysis.confidence}%`, background: biasStyle(ai.analysis.bias) }} />
            </div>
            <div className="mt-1 text-[11px] text-text2">
              Conviction: <span className="font-mono text-text1">{ai.analysis.conviction}</span>
            </div>
          </div>

          <div className="text-[12px] italic text-text2 border-l-2 border-border2 pl-2">
            "{ai.analysis.one_line}"
          </div>

          {/* Intraday plan */}
          {ai.analysis.intraday && (
            <div className="panel-inset rounded p-2 space-y-1 text-[11px] text-mono-tight">
              <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">Intraday Call</div>
              <KV k="Entry"  v={`${fmtINR(ai.analysis.intraday.entry_low)} – ${fmtINR(ai.analysis.intraday.entry_high)}`} />
              <KV k="T1"     v={`${fmtINR(ai.analysis.intraday.target_1)}  R:R ${(ai.analysis.intraday.rr_ratio_t1 ?? 0).toFixed(1)}:1`} color="var(--green)" />
              <KV k="T2"     v={`${fmtINR(ai.analysis.intraday.target_2)}  R:R ${(ai.analysis.intraday.rr_ratio_t2 ?? 0).toFixed(1)}:1`} color="var(--green)" />
              <KV k="SL"     v={fmtINR(ai.analysis.intraday.stop_loss)} color="var(--red)" />
              <KV k="Exit by" v={ai.analysis.intraday.exit_by ?? '—'} />
            </div>
          )}

          {/* Short-term plan */}
          {ai.analysis.shortterm && (
            <div className="panel-inset rounded p-2 space-y-1 text-[11px] text-mono-tight">
              <div className="text-[10px] uppercase tracking-wider text-text3 mb-1">Short-term ({ai.analysis.shortterm.horizon_days}d)</div>
              <div className="text-text2 leading-snug">
                <span className="text-text3">Trigger: </span>{ai.analysis.shortterm.trigger}
              </div>
              <KV k="Target" v={fmtINR(ai.analysis.shortterm.target)} color="var(--green)" />
              <KV k="SL"     v={fmtINR(ai.analysis.shortterm.stop_loss)} color="var(--red)" />
            </div>
          )}

          {/* Reasons */}
          <ul className="space-y-1 text-[12px] text-text2">
            {(ai.analysis.key_reasons ?? []).map((r, i) => (
              <li key={i} className="flex gap-2"><span className="text-green1">→</span><span>{r}</span></li>
            ))}
          </ul>

          {/* Risks */}
          <ul className="space-y-1 text-[12px] text-text2">
            {(ai.analysis.key_risks ?? []).map((r, i) => (
              <li key={i} className="flex gap-2"><span className="text-amber1">⚠</span><span>{r}</span></li>
            ))}
          </ul>

          {/* Signal summary */}
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            <SignalChip label="Trend"      value={ai.analysis.signal_summary.trend} />
            <SignalChip label="Momentum"   value={ai.analysis.signal_summary.momentum} />
            <SignalChip label="Volume"     value={ai.analysis.signal_summary.volume} />
            <SignalChip label="Volatility" value={ai.analysis.signal_summary.volatility} />
          </div>

          <div className="text-[10px] text-text3 text-right">
            {ai.model} · ₹{(ai.price_at_analysis ?? 0).toFixed(2)} at analysis
          </div>
        </div>
      )}
    </div>
  );
}

function KV({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text3">{k}</span>
      <span style={{ color: color || 'var(--text)' }}>{v}</span>
    </div>
  );
}

function SignalChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-inset rounded px-2 py-1 flex items-center justify-between">
      <span className="text-text3">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className="dot" style={{ background: dot(value) }} />
        <span className="text-text1">{value}</span>
      </span>
    </div>
  );
}
