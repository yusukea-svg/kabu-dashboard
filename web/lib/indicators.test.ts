import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { bollinger, ema, macd, rsi, sma } from "./indicators";

// Python 側と共有する合成データのフィクスチャ
const fixture = JSON.parse(
  readFileSync(join(__dirname, "../../batch/tests/fixtures/indicators.json"), "utf-8"),
) as { close: number[]; expected: Record<string, (number | null)[]> };

function expectSame(got: (number | null)[], expected: (number | null)[]) {
  expect(got.length).toBe(expected.length);
  got.forEach((v, i) => {
    if (expected[i] === null) expect(v).toBeNull();
    else expect(v).toBeCloseTo(expected[i]!, 6);
  });
}

describe("Python 実装との一致", () => {
  const c = fixture.close;
  const e = fixture.expected;
  it("SMA", () => {
    expectSame(sma(c, 5), e.sma5);
    expectSame(sma(c, 25), e.sma25);
    expectSame(sma(c, 75), e.sma75);
  });
  it("EMA", () => {
    expectSame(ema(c, 12), e.ema12);
    expectSame(ema(c, 26), e.ema26);
  });
  it("RSI", () => expectSame(rsi(c, 14), e.rsi14));
  it("MACD", () => {
    const m = macd(c);
    expectSame(m.macd, e.macd);
    expectSame(m.signal, e.macd_signal);
    expectSame(m.hist, e.macd_hist);
  });
  it("ボリンジャーバンド", () => {
    const b = bollinger(c);
    expectSame(b.upper, e.bb_upper);
    expectSame(b.mid, e.bb_mid);
    expectSame(b.lower, e.bb_lower);
  });
});
