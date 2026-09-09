import { useEffect, useMemo, useRef, useState } from "react";
import { TrendingUp } from "lucide-react";
import { init, use } from "echarts/core";
import { TreemapChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { type MarketOverview } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";

use([TreemapChart, TooltipComponent, CanvasRenderer]);
const fmt = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

export function SectorFlowPanel({ overview, loading, onRefresh }: {
  overview: MarketOverview | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const [direction, setDirection] = useState<"all" | "in" | "out">("all");
  const chartRef = useRef<HTMLDivElement>(null);

  const sectorTreemapRows = useMemo(() => (overview?.sectors || [])
    .filter((sector) => Number.isFinite(sector.net) && sector.net !== 0)
    .filter((sector) => direction === "all" || (direction === "in" ? sector.net > 0 : sector.net < 0))
    .sort((a, b) => Math.abs(b.net) - Math.abs(a.net))
    .slice(0, 15), [overview, direction]);
  const sectorTreemapOption = useMemo(() => ({
    animation: false,
    tooltip: {
      trigger: "item" as const,
      renderMode: "richText" as const,
      confine: true,
      backgroundColor: "rgba(15, 23, 42, .96)",
      borderColor: "rgba(255, 255, 255, .16)",
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: "#f8fafc", fontSize: 12, lineHeight: 20 },
      formatter: (params: unknown) => {
        const item = (params as { data?: { name?: string; net?: number; pct?: number | null } }).data;
        if (!item || typeof item.net !== "number") return "";
        const flow = item.net > 0 ? "净流入" : "净流出";
        const change = item.pct == null ? "" : `\n板块涨跌：${item.pct > 0 ? "+" : ""}${item.pct}%`;
        return `${item.name ?? ""}\n${flow}：${item.net > 0 ? "+" : ""}${fmt(item.net)} 亿元${change}`;
      },
    },
    series: [{
      type: "treemap" as const,
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      roam: false,
      nodeClick: false,
      sort: "desc" as const,
      visibleMin: 0,
      breadcrumb: { show: false },
      label: {
        show: true,
        color: "#e8e9ef",
        fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
        fontSize: 13,
        lineHeight: 24,
        padding: [8, 8],
        overflow: "truncate" as const,
        rich: {
          amount: { fontFamily: 'Consolas, monospace', fontWeight: 600, lineHeight: 32 },
          direction: { color: "#b4bac8", fontSize: 11, lineHeight: 20 },
        },
        formatter: (params: unknown) => {
          const item = (params as { data?: { name?: string; net?: number } }).data;
          if (!item || typeof item.net !== "number") return "";
          const name = (item.name ?? "").replace(/[{}]/g, "");
          return `${name}\n{amount|${item.net > 0 ? "+" : ""}${fmt(item.net)}}\n{direction|${item.net > 0 ? "净流入" : "净流出"} · 亿元}`;
        },
      },
      itemStyle: {
        borderColor: "#111722",
        borderWidth: 0,
        gapWidth: 5,
        borderRadius: 7,
      },
      emphasis: {
        itemStyle: {
          borderColor: "#f35d2b",
          borderWidth: 1,
        },
      },
      data: sectorTreemapRows.map((sector, index) => ({
        name: sector.name,
        value: Math.abs(sector.net!),
        net: sector.net!,
        pct: Number.isFinite(sector.pct) ? sector.pct : null,
        itemStyle: { color: sector.net! > 0 ? "#38262c" : "#1c3531" },
        label: { rich: { amount: { color: sector.net! > 0 ? "#ff9a91" : "#79d8ae", fontSize: index < 3 ? 26 : index < 9 ? 18 : 14 } } },
        emphasis: { itemStyle: { color: sector.net! > 0 ? "#4a3036" : "#25463e" } },
      })),
    }],
  }), [sectorTreemapRows]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = init(chartRef.current);
    chart.setOption(sectorTreemapOption);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(chartRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [sectorTreemapOption]);

  return (
    <div className="min-w-0">
      <p className="mb-3 text-xs leading-5 text-muted-foreground">同花顺行业资金流即时快照；数据源未标明主力口径，不作为主力净流入解读。</p>
      {/* 5. 板块资金趋势榜（行业） */}
      <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"><TrendingUp className="h-4 w-4" /> 板块资金趋势榜</h3>
        <span className="text-xs text-muted-foreground">{overview?.updated ? `获取于 ${overview.updated}` : ""}</span>
        <button type="button" onClick={onRefresh} disabled={loading}
          className="ml-auto rounded px-3 py-2 text-xs text-primary hover:bg-muted focus-visible:outline focus-visible:outline-primary disabled:opacity-50">刷新</button>
        <span className="text-[11px] text-muted-foreground/50">行业 · {direction === "all" ? "按净额绝对值" : direction === "in" ? "净流入" : "净流出"} Top 15</span>
      </div>
      <GlassCard className="mb-6 overflow-hidden">
        <div id="sector-treemap-help" className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">行业资金分布 <span className="ml-1 font-normal text-muted-foreground">/ 亿元</span></span>
          <div className="ml-auto flex gap-2">
            {(["in", "out"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={direction === value}
                title="点击筛选，再次点击恢复全部"
                onClick={() => setDirection((current) => current === value ? "all" : value)}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 hover:bg-muted focus-visible:outline focus-visible:outline-primary aria-pressed:bg-muted aria-pressed:text-foreground aria-pressed:ring-1 aria-pressed:ring-primary">
                <span className={value === "in" ? "h-2 w-2 rounded-sm bg-danger" : "h-2 w-2 rounded-sm bg-success"} aria-hidden="true" />
                {value === "in" ? "净流入" : "净流出"}
              </button>
            ))}
          </div>
        </div>
        {sectorTreemapRows.length === 0 ? (
          <p role="status" className="py-12 text-center text-sm text-muted-foreground">{loading ? "加载中…" : direction === "in" ? "暂无净流入板块" : direction === "out" ? "暂无净流出板块" : "暂无有效板块资金数据，请稍后刷新"}</p>
        ) : (
          <div>
            <div className="overflow-x-auto rounded-xl bg-[#111722] p-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-4" tabIndex={0} role="img" aria-label="板块资金矩形树图；矩形越大表示净流入或净流出金额越大，红色为净流入，绿色为净流出；窄屏可横向滚动" aria-describedby="sector-treemap-help">
              <div className="min-w-[640px]"><div ref={chartRef} style={{ height: 400 }} /></div>
            </div>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">面积表示净额绝对值 · 悬停或轻触查看详情 · 即时资金快照<span className="block sm:hidden">左右滑动查看完整矩阵</span></p>
          </div>
        )}
      </GlassCard>

    </div>
  );
}
