export function fmtINR(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e7)  return `${(n / 1e7).toFixed(2)}Cr`;   // Indian crore
  if (abs >= 1e5)  return `${(n / 1e5).toFixed(2)}L`;    // lakh
  if (abs >= 1e3)  return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(0);
}

export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}%`;
}

export function fmtChange(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}`;
}

export function isMarketOpen(now = new Date()): boolean {
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const day = ist.getDay();
  const total = ist.getHours() * 60 + ist.getMinutes();
  return day >= 1 && day <= 5 && total >= 555 && total < 930;
}

export function istClock(now = new Date()): string {
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  return ist.toLocaleTimeString('en-IN', { hour12: false }) + ' IST';
}

export function colorForChange(change: number | null | undefined): string {
  if (change === null || change === undefined) return 'var(--text2)';
  if (change > 0) return 'var(--green)';
  if (change < 0) return 'var(--red)';
  return 'var(--text2)';
}

export function gradeColor(grade: string): string {
  if (grade.startsWith('A')) return 'var(--green)';
  if (grade.startsWith('B')) return 'var(--amber)';
  return 'var(--red)';
}

export function scoreColor(score: number): string {
  if (score >= 70) return 'var(--green)';
  if (score >= 50) return 'var(--amber)';
  return 'var(--red)';
}

export function emaSparkline(values: number[], width = 60, height = 18): string {
  if (!values.length) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const dx = width / Math.max(values.length - 1, 1);
  return values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * dx).toFixed(2)},${(height - ((v - min) / span) * height).toFixed(2)}`)
    .join(' ');
}
