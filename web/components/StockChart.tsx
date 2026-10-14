"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type IChartApi,
  LineSeries,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { bollinger, macd, type Num, rsi, sma } from "@/lib/indicators";
import type { DailyBar } from "@/lib/types";

export type Overlays = { sma: boolean; bb: boolean; volume: boolean; rsi: boolean; macd: boolean };

const UP = "#d9463e"; // 日本の慣習：上昇=赤
const DOWN = "#2e8b57";

function line(times: Time[], values: Num[]) {
  return values.flatMap((v, i) => (v == null ? [] : [{ time: times[i], value: v }]));
}

function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export default function StockChart({ bars, overlays }: { bars: DailyBar[]; overlays: Overlays }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || bars.length === 0) return;
    const text = cssVar("--fg", "#222");
    const grid = cssVar("--grid", "#eee");
    const chart: IChartApi = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: text,
        fontSize: 11,
        panes: { separatorColor: grid },
      },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      localization: { locale: "ja-JP" },
    });

    const times = bars.map((b) => b.date as Time);
    const close = bars.map((b) => b.close);

    // 株価の呼値に合わせて、1,000円未満は小数1桁・それ以上は整数で表示
    const precision = close[close.length - 1] < 1000 ? 1 : 0;
    const priceFormat = { type: "price" as const, precision, minMove: precision ? 0.1 : 1 };

    chart.addSeries(CandlestickSeries, {
      priceFormat,
      upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN, wickUpColor: UP, wickDownColor: DOWN,
    }).setData(bars.map((b) => ({ time: b.date as Time, open: b.open, high: b.high, low: b.low, close: b.close })));

    const thin = { lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false, priceFormat };
    if (overlays.sma) {
      chart.addSeries(LineSeries, { ...thin, color: "#e69f00", title: "5" }).setData(line(times, sma(close, 5)));
      chart.addSeries(LineSeries, { ...thin, color: "#0072b2", title: "25" }).setData(line(times, sma(close, 25)));
      chart.addSeries(LineSeries, { ...thin, color: "#cc79a7", title: "75" }).setData(line(times, sma(close, 75)));
    }
    if (overlays.bb) {
      const b = bollinger(close);
      const bbStyle = { ...thin, color: "#999", lineStyle: 2 };
      chart.addSeries(LineSeries, bbStyle).setData(line(times, b.upper));
      chart.addSeries(LineSeries, bbStyle).setData(line(times, b.lower));
    }

    let pane = 1;
    if (overlays.volume) {
      chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false }, pane++).setData(
        bars.map((b, i) => ({
          time: b.date as Time,
          value: b.volume,
          color: i > 0 && b.close < bars[i - 1].close ? `${DOWN}88` : `${UP}88`,
        })),
      );
    }
    if (overlays.rsi) {
      const s = chart.addSeries(LineSeries, { ...thin, priceFormat: { type: "price", precision: 1, minMove: 0.1 }, color: "#7b61ff", title: "RSI" }, pane++);
      s.setData(line(times, rsi(close, 14)));
      s.createPriceLine({ price: 70, color: "#bbb", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
      s.createPriceLine({ price: 30, color: "#bbb", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    }
    if (overlays.macd) {
      const m = macd(close);
      const p = pane++;
      const mf = { type: "price" as const, precision: 2, minMove: 0.01 };
      chart.addSeries(HistogramSeries, { priceLineVisible: false, priceFormat: mf }, p).setData(
        m.hist.flatMap((v, i) => (v == null ? [] : [{ time: times[i], value: v, color: v >= 0 ? `${UP}88` : `${DOWN}88` }])),
      );
      chart.addSeries(LineSeries, { ...thin, priceFormat: mf, color: "#0072b2", title: "MACD" }, p).setData(line(times, m.macd));
      chart.addSeries(LineSeries, { ...thin, priceFormat: mf, color: "#e69f00", title: "Sig" }, p).setData(line(times, m.signal));
    }

    // メインのローソク足を大きく、サブ指標を小さく
    const panes = chart.panes();
    panes.forEach((pn, i) => pn.setStretchFactor(i === 0 ? 3 : 1));

    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 120), to: bars.length + 2 });
    return () => chart.remove();
  }, [bars, overlays]);

  const subPanes = [overlays.volume, overlays.rsi, overlays.macd].filter(Boolean).length;
  return <div ref={ref} className="chart" style={{ height: 300 + subPanes * 90 }} />;
}
