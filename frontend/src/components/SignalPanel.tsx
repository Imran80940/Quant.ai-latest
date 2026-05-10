import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { fetchIndicators } from '../api/client';
import type { Indicators } from '../types';

interface RowProps {
  label: string;
  value: string;
  detail?: string;
  bar?: number;          // 0..1
  barColor?: string;
  status?: 'green' | 'red' | 'amber' | 'neutral';
}

function statusToBg(s: RowProps['status']): string {
  switch (s) {
    case 'green':  return 'var(--green)';
    case 'red':    return 'var(--red)';
    case 'amber':  return 'var(--amber)';
    default:       return 'var(--text2)';
  }
}

function Row({ label, value, detail, bar, barColor, status }: RowProps) {
  return (
    <div className="grid grid-cols-[88px_56px_1fr] items-center gap-2 px-3 py-1.5 hover:bg-bg3/50 transition-colors">
      <span className="text-[11px] text-text3 uppercase tracking-wide">{label}</span>
      <span className="text-mono-tight text-sm" style={{ color: statusToBg(status) }}>{value}</span>
      <div className="flex items-center gap-2 min-w-0">
        {bar !== undefined && (
          <div className="bar flex-1 max-w-[80px]">
            <span style={{ width: `${Math.max(0, Math.min(100, bar * 100)).toFixed(0)}%`, background: barColor || statusToBg(status) }} />
          </div>
        )}
        {detail && <span className="text-[11px] text-text2 truncate">{detail}</span>}
      </div>
    </div>
  );
}

function rsiStatus(rsi: number): RowProps['status'] {
  if (rsi >= 75 || rsi <= 25) return 'red';
  if (rsi >= 40 && rsi <= 65) return 'green';
  return 'amber';
}

function adxStatus(adx: number): RowProps['status'] {
  if (adx > 25) return 'green';
  if (adx >= 15) return 'amber';
  return 'red';
}

function volStatus(mult: number): RowProps['status'] {
  if (mult > 1.3) return 'green';
  if (mult < 0.7) return 'red';
  return 'neutral';
}

function emaStackArrow(ind: Indicators): string {
  const a = (d: 'above' | 'below' | 'neutral') => (d === 'above' ? '↑' : d === 'below' ? '↓' : '·');
  return `${a(ind.price_vs_ema9)}${a(ind.price_vs_ema20)}${a(ind.price_vs_ema50)}${a(ind.price_vs_ema200)}`;
}

export default function SignalPanel() {
  const symbol = useStore((s) => s.activeSymbol);
  const indicators = useStore((s) => s.indicators);
  const setIndicators = useStore((s) => s.setIndicators);

  useEffect(() => {
    let cancelled = false;
    setIndicators(null);
    fetchIndicators(symbol)
      .then((res) => { if (!cancelled) setIndicators(res.indicators); })
      .catch(() => { if (!cancelled) setIndicators(null); });
    return () => { cancelled = true; };
  }, [symbol, setIndicators]);

  if (!indicators) {
    return (
      <div className="panel rounded-md">
        <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
          <span className="text-xs uppercase tracking-wider text-text2">Technical Signals</span>
          <span className="text-[10px] text-text3">loading…</span>
        </div>
        <div className="p-3 space-y-2">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="skeleton h-4 w-full rounded" />
          ))}
        </div>
      </div>
    );
  }

  const macdHistDir = indicators.macd_histogram > 0 ? '▲' : '▼';
  const macdStatus: RowProps['status'] =
    indicators.macd_histogram > 0 && indicators.macd_crossover === 'bullish' ? 'green' : 'red';

  return (
    <div className="panel rounded-md">
      <div className="px-3 py-2 border-b border-border1 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-text2">Technical Signals</span>
        <span className="text-[10px] text-text3">6mo daily</span>
      </div>
      <div className="divide-y divide-border1/30">
        <Row
          label="RSI (14)"
          value={indicators.rsi.toFixed(1)}
          bar={indicators.rsi / 100}
          status={rsiStatus(indicators.rsi)}
          detail={
            indicators.rsi > 70 ? 'Overbought'
            : indicators.rsi < 30 ? 'Oversold'
            : indicators.rsi >= 40 && indicators.rsi <= 65 ? 'Bullish zone'
            : 'Neutral'
          }
        />
        <Row
          label="MACD"
          value={`${indicators.macd_histogram >= 0 ? '+' : ''}${indicators.macd_histogram.toFixed(2)}`}
          status={macdStatus}
          detail={`${macdHistDir} ${indicators.macd_crossover} crossover`}
        />
        <Row
          label="Stoch RSI"
          value={indicators.stoch_rsi.toFixed(1)}
          bar={indicators.stoch_rsi / 100}
          status={indicators.stoch_rsi > 80 ? 'red' : indicators.stoch_rsi > 50 ? 'green' : indicators.stoch_rsi < 20 ? 'red' : 'amber'}
          detail={indicators.stoch_rsi > 80 ? 'Overbought' : indicators.stoch_rsi < 20 ? 'Oversold' : indicators.stoch_rsi > 50 ? 'Bullish' : 'Bearish'}
        />
        <Row
          label="ADX"
          value={indicators.adx.toFixed(1)}
          bar={indicators.adx / 50}
          status={adxStatus(indicators.adx)}
          detail={`${indicators.trend_strength} trend`}
        />
        <Row
          label="Bollinger"
          value={`${indicators.bb_position_pct.toFixed(0)}%`}
          bar={indicators.bb_position_pct / 100}
          status={indicators.bb_squeeze ? 'amber' : indicators.bb_position_pct > 80 ? 'green' : indicators.bb_position_pct < 20 ? 'red' : 'neutral'}
          detail={
            indicators.bb_squeeze ? 'Squeeze — breakout setup'
            : indicators.bb_position_pct > 80 ? 'Near upper band'
            : indicators.bb_position_pct < 20 ? 'Near lower band' : 'Mid range'
          }
        />
        <Row
          label="EMA Stack"
          value={emaStackArrow(indicators)}
          status={
            (indicators.price_vs_ema20 === 'above' && indicators.price_vs_ema50 === 'above' && indicators.price_vs_ema200 === 'above')
              ? 'green'
              : (indicators.price_vs_ema20 === 'below' && indicators.price_vs_ema50 === 'below')
              ? 'red'
              : 'amber'
          }
          detail={`9/20/50/200 — ${indicators.ema_50.toFixed(0)} / ${indicators.ema_200.toFixed(0)}`}
        />
        <Row
          label="Volume"
          value={`${indicators.volume_vs_avg20.toFixed(2)}x`}
          bar={Math.min(indicators.volume_vs_avg20 / 3, 1)}
          status={volStatus(indicators.volume_vs_avg20)}
          detail={`OBV ${indicators.obv_trend}`}
        />
        <Row
          label="ATR"
          value={`${indicators.atr_pct.toFixed(2)}%`}
          status={indicators.atr_pct > 4 ? 'red' : indicators.atr_pct < 1 ? 'amber' : 'neutral'}
          detail={`₹${indicators.atr.toFixed(1)} range`}
        />
        <Row
          label="VWAP"
          value={indicators.price_vs_vwap === 'above' ? 'Above' : 'Below'}
          status={indicators.price_vs_vwap === 'above' ? 'green' : 'red'}
          detail={`₹${indicators.vwap.toFixed(0)}`}
        />
        <Row
          label="Supertrend"
          value={indicators.supertrend === 'bullish' ? '▲' : indicators.supertrend === 'bearish' ? '▼' : '·'}
          status={indicators.supertrend === 'bullish' ? 'green' : indicators.supertrend === 'bearish' ? 'red' : 'neutral'}
          detail={indicators.supertrend}
        />
      </div>
    </div>
  );
}
