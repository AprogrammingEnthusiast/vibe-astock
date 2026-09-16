// Adapted from Vibe-Research EventsPanel, MIT (c) 2026 simonlin1212.
// Full upstream license notice: vr/probability.py.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, RefreshCw } from "lucide-react";
import { api, type MacroProbability, type MacroProbItem } from "@/lib/api";
import { displayedHeadlineTranslation, hasChinese, loadHeadlineTranslationCache, missingHeadlineTranslations, saveHeadlineTranslationCache, splitHeadlineBatches } from "@/lib/headline-translation";
import { hasLlm, translateHeadlineBatch } from "@/lib/llm";

interface TitleTranslation {
  status: "running" | "done" | "partial" | "need-key";
  done: number;
  total: number;
  error?: string;
}

export function EventsPanel() {
  const [data, setData] = useState<MacroProbability | null>(null);
  const [err, setErr] = useState("");
  const [refreshing, setRefreshing] = useState(true);
  const refresh = useCallback(async () => {
    setRefreshing(true); setErr("");
    try { setData(await api.macroProbability(true)); }
    catch (e) { setErr(e instanceof Error ? e.message : "刷新失败"); }
    finally { setRefreshing(false); }
  }, []);
  useEffect(() => {
    let stopped = false;
    api.macroProbability().then((archive) => { if (!stopped) setData(archive); })
      .catch(() => { /* 存档读取失败仍尝试实时取数 */ })
      .finally(() => { if (!stopped) void refresh(); });
    return () => { stopped = true; };
  }, [refresh]);
  const [translation, setTranslation] = useState<TitleTranslation>();
  const translationCache = useRef(loadHeadlineTranslationCache());
  const latestTranslationRun = useRef("");
  const attemptedGeneration = useRef("");
  const [, redrawTranslations] = useState(0);

  const translateEvents = useCallback(async (items: MacroProbItem[], generation: string, force = false) => {
    if (!hasLlm()) {
      setTranslation({ status: "need-key", done: 0, total: items.length });
      return;
    }
    const runId = `${generation}\u0000${force ? Date.now() : "auto"}`;
    latestTranslationRun.current = runId;
    const cache = translationCache.current;
    const completedThisRun = new Set<string>();
    const doneCount = () => items.filter((item) =>
      hasChinese(item.title) || (force ? completedThisRun.has(item.title) : cache.has(item.title)),
    ).length;
    const targets = missingHeadlineTranslations(items, cache, force);
    if (!targets.length) {
      setTranslation({ status: "done", done: items.length, total: items.length });
      return;
    }

    setTranslation({ status: "running", done: doneCount(), total: items.length });
    const errors: string[] = [];
    for (const batch of splitHeadlineBatches(targets)) {
      try {
        const got = await translateHeadlineBatch(batch);
        for (const item of batch) {
          const zh = got.get(item.id);
          if (zh) {
            cache.set(item.title, zh);
            completedThisRun.add(item.title);
          }
        }
        saveHeadlineTranslationCache(cache);
        redrawTranslations((n) => n + 1);
      } catch (e) {
        errors.push(e instanceof Error ? e.message : "翻译失败");
      }
      if (latestTranslationRun.current === runId) {
        setTranslation({ status: "running", done: doneCount(), total: items.length });
      }
    }
    if (latestTranslationRun.current !== runId) return;
    const done = doneCount();
    setTranslation(done === items.length
      ? { status: "done", done, total: items.length }
      : { status: "partial", done, total: items.length, error: errors[0] ?? "模型漏回了部分标题" });
  }, []);

  useEffect(() => {
    if (!data?.items.length || refreshing || attemptedGeneration.current === data.updated) return;
    const timer = window.setTimeout(() => {
      attemptedGeneration.current = data.updated;
      void translateEvents(data.items, data.updated);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [data, refreshing, translateEvents]);

  const byTopic = new Map<string, MacroProbItem[]>();
  for (const it of data?.items || []) byTopic.set(it.topic, [...(byTopic.get(it.topic) ?? []), it]);

  return (
    <div className="mt-3">
      <p role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        <span>{`共 ${data?.items.length || 0} 份合约`}</span>
        {data?.partial && <span className="text-warning">· 数据覆盖不完整，这不是完整清单</span>}
        <span className="text-[11px] text-muted-foreground/60">{data?.updated ? `更新于 ${new Date(data.updated).toLocaleString("zh-CN")}` : "尚无存档"}</span>
        {refreshing && (
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
            <Loader2 aria-hidden="true" className="h-3 w-3 animate-spin motion-reduce:animate-none" /> {data?.items.length ? "刷新中（下面是上次的存档）" : "正在抓取公开报价…"}
          </span>
        )}

        <button onClick={refresh} disabled={refreshing}
          className="inline-flex min-h-7 items-center gap-1 rounded-lg border border-border px-2 py-0.5 text-xs hover:text-foreground disabled:opacity-50">
          <RefreshCw aria-hidden="true" className="h-3 w-3" /> 刷新
        </button>
      </p>

      {err && <p role="alert" className="mt-3 text-sm text-destructive">{err}{data?.items.length ? "；仍显示上次存档，请留意报价时间。" : ""}</p>}
      {!data?.items.length && !refreshing && !err && <p className="mt-3 text-sm text-muted-foreground">本轮没有取得符合筛选条件的报价，不代表没有相关事件。</p>}
      {!!data?.warnings.length && <details className="mt-3 text-xs text-warning"><summary className="cursor-pointer">数据覆盖说明</summary><ul className="mt-2 space-y-1">{data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}

      <div className="mt-2 flex min-h-7 flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        {translation?.status === "running" ? (
          <span className="inline-flex items-center gap-1.5 text-primary"><Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" /> AI 正在翻译合约标题 {translation.done}/{translation.total}</span>
        ) : translation?.status === "done" ? (
          <span className="text-success">AI 合约标题翻译 {translation.done}/{translation.total}</span>
        ) : translation?.status === "partial" ? (
          <span className="text-warning">标题已翻译 {translation.done}/{translation.total}，其余保留原文{translation.error ? `（${translation.error}）` : ""}</span>
        ) : translation?.status === "need-key" ? (
          <span>标题尚未翻译 · <Link to="/settings" className="text-primary">先接入 AI</Link></span>
        ) : (
          <span>合约标题将在数据刷新后自动翻译</span>
        )}
        {(translation?.status === "partial" || translation?.status === "done" || translation?.status === "need-key") && (
          <button
            type="button"
            onClick={() => data && void translateEvents(data.items, data.updated, translation.status === "done")}
            disabled={refreshing}
            className="text-muted-foreground hover:text-primary disabled:opacity-50"
          >
            {translation.status === "done" ? "重新翻译" : "继续翻译"}
          </button>
        )}
      </div>

      {[...byTopic.entries()].map(([topic, items]) => (
        <div key={topic} className="mt-4">
          <h4 className="mb-2 text-xs font-semibold text-muted-foreground">{topic}</h4>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-sm">
              <thead className="text-[11px] text-muted-foreground/70">
                <tr>
                  <th scope="col" className="px-2 py-1 text-left font-normal">合约在问什么</th>
                  <th scope="col" className="px-2 py-1 text-right font-normal">概率</th>
                  <th scope="col" className="px-2 py-1 text-left font-normal">结算日</th>
                  <th scope="col" className="px-2 py-1 text-right font-normal">24h 成交量</th>
                  <th scope="col" className="px-2 py-1 text-left font-normal">来源</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const zh = displayedHeadlineTranslation(it, translationCache.current);
                  return (
                  <tr key={`${it.title}-${i}`} className="border-t border-border/40">
                    <td className="px-2 py-2">
                      <span className="block">{zh || it.title}{it.leg && <span className="ml-1 text-[11px] text-muted-foreground/60">（{it.leg}）</span>}</span>
                      {zh && zh !== it.title && <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground/65">{it.title}</span>}
                    </td>
                    <td className="px-2 py-2 text-right font-mono font-semibold">
                      {it.prob === null ? "—" : `${(it.prob * 100).toFixed(1)}%`}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 font-mono text-xs text-muted-foreground">{it.settle || "—"}</td>
                    <td className="px-2 py-2 text-right font-mono text-[11px] text-muted-foreground">
                      {it.volume === null ? "未提供" : it.volume.toLocaleString("en-US")}{it.volume === 0 && <span className="block text-warning">当日无成交</span>}
                    </td>
                    <td className="px-2 py-2 text-[11px] text-muted-foreground">{it.source}<span className="mt-1 block">{it.price_type === "ask" ? "卖方报价" : it.price_type === "last" ? "最新成交价" : "Yes 价格"}</span><time dateTime={it.as_of} className="mt-1 block whitespace-nowrap">{new Date(it.as_of).toLocaleString("zh-CN")}</time></td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {/* 🔴 护栏与数字同屏 —— 照抄取数层原话，不改写 */}
      {!!data?.how_to_read.length && (
        <div className="mt-4 rounded-lg border border-border/60 bg-muted/20 p-3">
          <p className="mb-1 text-xs font-semibold text-muted-foreground">怎么读这组数</p>
          {data.how_to_read.map((h: string) => (
            <p key={h} className="text-[11px] leading-relaxed text-muted-foreground/80">{h}</p>
          ))}
        </div>
      )}
    </div>
  );
}
