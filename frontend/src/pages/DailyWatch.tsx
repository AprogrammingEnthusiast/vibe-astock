import { useEffect, useRef, useState } from "react";
import { pctColor } from "@/lib/colors";
import { Wallet, Star, Building2, Flame, BarChart3, BellRing, Loader2, Plus, X } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, type MonitorSnapshot, type WatchRow } from "@/lib/api";
import { loadWatch, saveWatch, addCodes } from "@/lib/watchlist";

const fmt = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const yi = (v: number | null | undefined) => (v == null ? "—" : `${fmt(v / 1e8)} 亿`);

const pctText = (p: number | null | undefined) => (p == null ? "—" : `${p > 0 ? "+" : ""}${p}%`);

const PHASE_LABEL: Record<string, string> = { open: "交易中", break: "午间休市", closed: "已收盘" };
const KIND_STYLE: Record<string, string> = {
  急拉: "border-danger/50 bg-danger/10 text-danger",
  急跌: "border-success/50 bg-success/10 text-success",
  封板: "border-primary/50 bg-primary/10 text-primary",
  开板: "border-secondary/50 bg-secondary/10 text-secondary",
};

/** 星标：加/移自选（所有出现股票的地方都挂它） */
function WatchStar({ code, watch, onToggle }: { code: string; watch: string[]; onToggle: (c: string) => void }) {
  const inWatch = watch.includes(code);
  return (
    <button
      onClick={() => onToggle(code)}
      title={inWatch ? "移出自选" : "加入自选"}
      className={`rounded p-0.5 transition-colors ${inWatch ? "text-primary" : "text-muted-foreground/40 hover:text-primary"}`}
    >
      <Star className="h-3.5 w-3.5" fill={inWatch ? "currentColor" : "none"} />
    </button>
  );
}

interface QuoteTableProps {
  rows: WatchRow[];
  cols: ("pnl" | "boards" | "amount")[];
  watch: string[];
  onToggleWatch: (code: string) => void;
  onRemove?: (code: string) => void; // 持仓行删除
}

function QuoteTable({ rows, cols, watch, onToggleWatch, onRemove }: QuoteTableProps) {
  if (rows.length === 0) return <p className="py-4 text-center text-xs text-muted-foreground/60">暂无标的</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
            <th className="whitespace-nowrap px-2 py-1.5 font-medium">名称</th>
            {cols.includes("boards") && <th className="whitespace-nowrap px-2 py-1.5 font-medium">连板</th>}
            <th className="whitespace-nowrap px-2 py-1.5 font-medium">现价</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-medium">今日</th>
            {cols.includes("pnl") && <th className="whitespace-nowrap px-2 py-1.5 font-medium">浮动盈亏</th>}
            {cols.includes("amount") && <th className="whitespace-nowrap px-2 py-1.5 font-medium">成交额</th>}
            <th className="px-1 py-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.code} className="border-b border-border/30">
              <td className="whitespace-nowrap px-2 py-1.5">
                <span className="font-medium">{r.name || r.code}</span>{" "}
                <span className="text-xs text-muted-foreground/50">{r.code}</span>
                {r.is_limit === true && <span className="ml-1 rounded border border-primary/50 bg-primary/10 px-1 text-[10px] text-primary">封</span>}
                {r.is_limit === false && <span className="ml-1 rounded border border-secondary/50 bg-secondary/10 px-1 text-[10px] text-secondary">开</span>}
              </td>
              {cols.includes("boards") && (
                <td className="whitespace-nowrap px-2 py-1.5 font-mono font-bold text-primary">{r.boards} 板</td>
              )}
              <td className="px-2 py-1.5 font-mono">{r.price ?? "—"}</td>
              <td className={`px-2 py-1.5 font-mono ${pctColor(r.pct)}`}>{pctText(r.pct)}</td>
              {cols.includes("pnl") && (
                <td className={`px-2 py-1.5 font-mono ${pctColor(r.pnl_pct)}`}>{pctText(r.pnl_pct)}</td>
              )}
              {cols.includes("amount") && (
                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-muted-foreground">{yi(r.amount)}</td>
              )}
              <td className="whitespace-nowrap px-1 py-1.5 text-right">
                <span className="inline-flex items-center gap-0.5">
                  <WatchStar code={r.code} watch={watch} onToggle={onToggleWatch} />
                  {onRemove && (
                    <button onClick={() => onRemove(r.code)} title="删除" className="rounded p-0.5 text-muted-foreground/40 hover:text-danger">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DailyWatch() {
  const [snap, setSnap] = useState<MonitorSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [watch, setWatch] = useState<string[]>(() => loadWatch());
  const [watchInput, setWatchInput] = useState("");
  const [hold, setHold] = useState({ code: "", shares: "", cost: "" });
  const [holdErr, setHoldErr] = useState<string | null>(null);
  const [holdBusy, setHoldBusy] = useState(false);
  const watchRef = useRef(watch);
  watchRef.current = watch;

  useEffect(() => {
    const pull = () => {
      api.monitorSnapshot(watchRef.current.join(","))
        .then((d) => { setSnap(d); setErr(null); })
        .catch((e) => setErr(e instanceof Error ? e.message : "读取失败"));
    };
    pull();
    const t = window.setInterval(pull, 3000);
    return () => window.clearInterval(t);
  }, []);

  const toggleWatch = async (code: string) => {
    const next = watch.includes(code) ? watch.filter((c) => c !== code) : [...watch, code];
    try { await saveWatch(next); setWatch(next); }
    catch (e) { setErr(e instanceof Error ? e.message : "保存失败"); }
  };

  const addWatchInput = async () => {
    if (!watchInput.trim()) return;
    const { next } = addCodes(watch, watchInput);
    try { await saveWatch(next); }
    catch (e) { setErr(e instanceof Error ? e.message : "保存失败"); return; }
    setWatch(next);
    setWatchInput("");
  };

  const addHold = async () => {
    setHoldErr(null);
    if (!/^\d{6}$/.test(hold.code.trim())) { setHoldErr("代码需为 6 位数字"); return; }
    const shares = parseFloat(hold.shares);
    const cost = parseFloat(hold.cost);
    if (!(shares > 0) || !(cost > 0)) { setHoldErr("股数与成本需为正数"); return; }
    setHoldBusy(true);
    try {
      await api.addHolding(hold.code.trim(), shares, cost);
      setHold({ code: "", shares: "", cost: "" });
    } catch (e) {
      setHoldErr(e instanceof Error ? e.message : "录入失败");
    } finally {
      setHoldBusy(false);
    }
  };

  const removeHold = async (code: string) => {
    try { await api.removeHolding(code); } catch { /* 下一轮快照自然纠正 */ }
  };

  const phase = snap?.phase || "closed";
  const inputCls = "rounded-lg border border-border/60 bg-background/50 px-2 py-1 text-xs outline-none focus:border-primary/60";

  return (
    <div>
      <PageHeader
        title="每日盯盘"
        subtitle="持仓 · 自选 · 500亿大票异动 · 三板+ · 昨日成交前十 —— 交易时段每 3 秒实时刷新（L1 快照极限频率）"
      />

      {/* 状态条 */}
      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${phase === "open" ? "border-danger/50 bg-danger/10 text-danger" : "border-border/60"}`}>
          {phase === "open" && <Loader2 className="h-3 w-3 animate-spin" />}
          {PHASE_LABEL[phase]}
        </span>
        {snap?.ts && <span>快照 {snap.ts}</span>}
        <span>监控池：500亿大票 {snap?.bigcap.total ?? 0} 只 + 持仓/自选/连板/昨十</span>
        <span className="inline-flex items-center gap-1"><BellRing className="h-3.5 w-3.5" /> 今日异动 {snap?.alerts.length ?? 0} 条</span>
        {err && <span className="text-danger">{err}</span>}
      </div>

      {/* 异动流 */}
      <GlassCard className="mb-4" glow>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <BellRing className="h-4 w-4 text-primary" /> 异动流
          <span className="text-xs font-normal text-muted-foreground">急拉/急跌（3分钟±1.5%）· 封板/开板 · 同票同类 5 分钟冷却 · 客观数据事件，非推荐/非预测</span>
        </div>
        {(snap?.alerts.length ?? 0) === 0 ? (
          <p className="py-3 text-center text-xs text-muted-foreground/60">
            {phase === "open" ? "暂无异动（开盘初需积累约 1 分钟数据）" : "非交易时段 · 开盘后自动开始监控"}
          </p>
        ) : (
          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {snap!.alerts.map((a, i) => (
              <div key={`${a.ts}-${a.code}-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-xs text-muted-foreground">{a.ts}</span>
                <span className={`rounded border px-1.5 py-0.5 text-xs font-medium ${KIND_STYLE[a.kind] || "border-border/60"}`}>{a.kind}</span>
                <span className="font-medium">{a.name}</span>
                <span className="text-xs text-muted-foreground/50">{a.code}</span>
                <WatchStar code={a.code} watch={watch} onToggle={toggleWatch} />
                <span className="text-xs text-muted-foreground">{a.msg}</span>
                <span className="ml-auto flex gap-1">
                  {a.sources.map((s) => (
                    <span key={s} className="rounded-full border border-secondary/40 bg-secondary/10 px-1.5 py-0.5 text-[10px] text-secondary">{s}</span>
                  ))}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* 持仓 / 自选 */}
      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <GlassCard>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold">
            <Wallet className="h-4 w-4 text-primary" /> 持仓股
            <span className="ml-auto flex items-center gap-1.5 font-normal">
              <input className={`w-20 ${inputCls}`} placeholder="代码" value={hold.code}
                     onChange={(e) => setHold({ ...hold, code: e.target.value })} />
              <input className={`w-16 ${inputCls}`} placeholder="股数" value={hold.shares}
                     onChange={(e) => setHold({ ...hold, shares: e.target.value })} />
              <input className={`w-20 ${inputCls}`} placeholder="成本价" value={hold.cost}
                     onChange={(e) => setHold({ ...hold, cost: e.target.value })}
                     onKeyDown={(e) => e.key === "Enter" && addHold()} />
              <button onClick={addHold} disabled={holdBusy}
                      className="inline-flex items-center gap-1 rounded-lg border border-primary/50 bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-40">
                {holdBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}录入
              </button>
            </span>
          </div>
          {holdErr && <p className="mb-1 text-xs text-danger">{holdErr}</p>}
          <p className="mb-1 text-[10px] text-muted-foreground/60">录入/删除后约 3 秒生效（下一轮快照）· 数据只存本机</p>
          <QuoteTable rows={snap?.holdings ?? []} cols={["pnl"]} watch={watch} onToggleWatch={toggleWatch} onRemove={removeHold} />
        </GlassCard>
        <GlassCard>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold">
            <Star className="h-4 w-4 text-primary" /> 自选股
            <span className="ml-auto flex items-center gap-1.5 font-normal">
              <input className={`w-44 ${inputCls}`} placeholder="代码，可粘贴一串（空格/逗号分隔）" value={watchInput}
                     onChange={(e) => setWatchInput(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && addWatchInput()} />
              <button onClick={addWatchInput}
                      className="inline-flex items-center gap-1 rounded-lg border border-primary/50 bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20">
                <Plus className="h-3 w-3" />添加
              </button>
            </span>
          </div>
          <p className="mb-1 text-[10px] text-muted-foreground/60">与「自选股」页同一份本地数据 · 各表行尾 ★ 一键加自选</p>
          <QuoteTable rows={snap?.watchlist ?? []} cols={[]} watch={watch} onToggleWatch={toggleWatch} />
        </GlassCard>
      </div>

      {/* 大票 / 三板+ / 昨十 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Building2 className="h-4 w-4 text-primary" /> 500亿大票
            <span className="text-xs font-normal text-muted-foreground">池 {snap?.bigcap.total ?? 0} 只 · 异动见上方异动流 · 下为今日涨幅前十</span>
          </div>
          <QuoteTable rows={snap?.bigcap.top ?? []} cols={["amount"]} watch={watch} onToggleWatch={toggleWatch} />
        </GlassCard>
        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Flame className="h-4 w-4 text-primary" /> 三板以上
            <span className="text-xs font-normal text-muted-foreground">封/开实时</span>
          </div>
          <QuoteTable rows={snap?.lianban3 ?? []} cols={["boards", "amount"]} watch={watch} onToggleWatch={toggleWatch} />
        </GlassCard>
        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <BarChart3 className="h-4 w-4 text-primary" /> {snap?.turnover.label || "昨日成交前十"}
          </div>
          <QuoteTable rows={snap?.turnover.stocks ?? []} cols={["amount"]} watch={watch} onToggleWatch={toggleWatch} />
        </GlassCard>
      </div>

      <Disclaimer />
    </div>
  );
}
