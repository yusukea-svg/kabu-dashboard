// テクニカル指標（batch/src/kabu_batch/indicators.py と同じ定義）。
// 両者の一致は batch/tests/fixtures/indicators.json で検証している。

export type Num = number | null;

export function sma(values: number[], n: number): Num[] {
  const out: Num[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= n) sum -= values[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

export function ema(values: number[], n: number): Num[] {
  const out: Num[] = new Array(values.length).fill(null);
  if (values.length < n) return out;
  const k = 2 / (n + 1);
  let prev = values.slice(0, n).reduce((a, b) => a + b, 0) / n;
  out[n - 1] = prev;
  for (let i = n; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export function rsi(values: number[], n = 14): Num[] {
  const out: Num[] = new Array(values.length).fill(null);
  if (values.length <= n) return out;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    gains.push(Math.max(d, 0));
    losses.push(Math.max(-d, 0));
  }
  let g = gains.slice(0, n).reduce((a, b) => a + b, 0) / n;
  let l = losses.slice(0, n).reduce((a, b) => a + b, 0) / n;
  const value = (g: number, l: number) => (l === 0 ? (g > 0 ? 100 : 50) : 100 - 100 / (1 + g / l));
  out[n] = value(g, l);
  for (let i = n + 1; i < values.length; i++) {
    g = (g * (n - 1) + gains[i - 1]) / n;
    l = (l * (n - 1) + losses[i - 1]) / n;
    out[i] = value(g, l);
  }
  return out;
}

export function macd(values: number[], fast = 12, slow = 26, signal = 9) {
  const f = ema(values, fast);
  const s = ema(values, slow);
  const line: Num[] = values.map((_, i) => (f[i] !== null && s[i] !== null ? f[i]! - s[i]! : null));
  const start = line.findIndex((v) => v !== null);
  const sig: Num[] = new Array(values.length).fill(null);
  if (start >= 0) {
    const e = ema(line.slice(start) as number[], signal);
    e.forEach((v, i) => (sig[start + i] = v));
  }
  const hist: Num[] = line.map((v, i) => (v !== null && sig[i] !== null ? v - sig[i]! : null));
  return { macd: line, signal: sig, hist };
}

export function bollinger(values: number[], n = 20, k = 2) {
  const mid = sma(values, n);
  const upper: Num[] = new Array(values.length).fill(null);
  const lower: Num[] = new Array(values.length).fill(null);
  for (let i = n - 1; i < values.length; i++) {
    const m = mid[i]!;
    let v = 0;
    for (let j = i - n + 1; j <= i; j++) v += (values[j] - m) ** 2;
    const sd = Math.sqrt(v / n); // 母標準偏差
    upper[i] = m + k * sd;
    lower[i] = m - k * sd;
  }
  return { upper, mid, lower };
}
