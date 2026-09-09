import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ChevronDown, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, Sparkles, Terminal, Trash2 } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { toast } from "sonner";
import { sharedWebsite } from "@/lib/account";
import { AccountPanel } from "@/components/AccountPanel";
import { loadLlm, saveLlm, clearLlm, staleBlockedProvider } from "@/lib/llm";
import { loadAccessKey, saveAccessKey, authHeaders } from "@/lib/api";
import { subscriptionModels, apiModels, PROVIDER_BASE, isCliProvider, aiModels, cliKindOf,
  primeCliAvailability, cliAvailability, cliAvailState,
  fetchApiModels, startCodexDeviceAuth,
  type CliAvailability, type CliAvailState, type ProviderId } from "@/lib/ai-models";

const INPUT = "w-full rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20";
const SELECT = `${INPUT} h-11 appearance-none rounded-xl border-border/80 bg-card/70 pl-3 pr-10 font-medium shadow-sm hover:border-primary/40`;
const SELECT_ICON = "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground";
const MODEL_BUTTON = "inline-flex h-11 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-xl border border-border/80 bg-muted/35 px-3.5 text-xs font-semibold text-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:cursor-wait disabled:opacity-50";

export function Settings() {
  const existing = loadLlm();
  const existingIsCli = existing ? isCliProvider(existing.provider) : false;
  const [staleBlocked, setStaleBlocked] = useState<string | null>(staleBlockedProvider());

  const [mode, setMode] = useState<"api" | "subscription">(
    (existing && existingIsCli) || staleBlocked ? "subscription" : "api");
  const existingCli = existing && existingIsCli
    ? subscriptionModels.find((m) => m.provider === existing.provider)
    : undefined;
  const [cliId, setCliId] = useState(existingCli?.id ?? "");
  const initialCliModel = existingCli?.provider === "cli-codex" && existing?.model !== existingCli.id ? existing?.model ?? "" : "";
  const [cliModel, setCliModel] = useState(initialCliModel);
  const [cliModels, setCliModels] = useState<string[]>(initialCliModel ? [initialCliModel] : []);
  // API：选中的模型 id + 可编辑的 baseURL / model / key
  const firstApi = apiModels[0];
  // ponytail: custom model not in preset list → select won't match any option → fallback to first item
  const matchedApi = existing && !existingIsCli ? apiModels.find((m) => m.id === existing.model) : null;
  const [apiId, setApiId] = useState(matchedApi ? matchedApi.id : "custom");
  const [baseURL, setBaseURL] = useState(existing && !existingIsCli ? existing.baseURL : (PROVIDER_BASE[firstApi.provider] || ""));
  const initialApiModel = existing && !existingIsCli ? existing.model : firstApi.id;
  const [modelName, setModelName] = useState(initialApiModel);
  const [availableApiModels, setAvailableApiModels] = useState<string[]>([initialApiModel]);
  const [apiKey, setApiKey] = useState(existing && !existingIsCli ? existing.apiKey : "");
  // 后端访问密钥（对应部署时的 VR_API_KEY）；本机自用不设鉴权时留空
  const [accessKey, setAccessKey] = useState(loadAccessKey());

  const [cliAvail, setCliAvail] = useState<CliAvailability | null>(cliAvailability());
  const [availState, setAvailState] = useState<CliAvailState>(cliAvailState());
  const [loginStarting, setLoginStarting] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [choosingModel, setChoosingModel] = useState(false);
  const connectingCodex = useRef(false);
  const modelDialog = useRef<HTMLDialogElement>(null);
  const codexStatus = cliAvail?.clis.find((c) => c.kind === "codex");
  
  const refreshAvail = () =>
    primeCliAvailability(authHeaders()).then((d) => {
      setCliAvail(d);
      setAvailState(cliAvailState());
      setStaleBlocked(staleBlockedProvider());
      return d;
    });

  useEffect(() => {
    void refreshAvail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (codexStatus?.status !== "login_pending") return;
    const timer = window.setInterval(() => void refreshAvail(), 2_000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codexStatus?.status]);

  useEffect(() => {
    if (!codexStatus?.models?.length) return;
    setCliModels(codexStatus.models);
    setCliModel((current) => codexStatus.models!.includes(current) ? current : codexStatus.model || "");
  }, [codexStatus?.model, codexStatus?.models]);

  useEffect(() => {
    if (codexStatus?.status === "login_pending") connectingCodex.current = true;
    if (!codexStatus?.authenticated || !codexStatus.allowed) return;
    if (connectingCodex.current || (!existing && !cliId)) {
      connectingCodex.current = false;
      setCliId("codex"); setMode("subscription"); setChoosingModel(true);
    }
  }, [codexStatus?.status, codexStatus?.authenticated, codexStatus?.allowed, existing, cliId]);

  useEffect(() => {
    if (choosingModel && modelDialog.current && !modelDialog.current.open) modelDialog.current.showModal();
  }, [choosingModel]);

  
  // 卡片上那句"支持哪些 CLI"，直接由服务端上报的 allowed 列表生成
  const allowedCliLabel = (() => {
    if (availState !== "ready") return "以后端上报为准";
    const ok = subscriptionModels.filter((m) => {
      const st = cliAvail?.clis.find((c) => c.kind === cliKindOf(m.provider));
      return st?.allowed && st.installed;
    });
    return ok.length ? ok.map((m) => m.name).join(" / ") : "当前后端未放行任何 CLI";
  })();

  const cliState = (m: (typeof subscriptionModels)[number]): { ok: boolean; why: string | null } => {
    if (m.comingSoon) return { ok: false, why: "开发中" };
    if (availState === "loading" || availState === "idle") return { ok: false, why: "正在确认本机可用的 CLI…" };
    if (availState === "failed") return { ok: false, why: "无法向后端确认可用性" };
    const st = cliAvail?.clis.find((c) => c.kind === cliKindOf(m.provider));
    if (!st) return { ok: false, why: "后端不认识这个 CLI" };
    if (!st.allowed) return { ok: false, why: m.blocked ?? st.reason ?? "已禁用" };
    if (!st.installed) return { ok: false, why: "本机未安装这个命令" };
    if (m.provider === "cli-codex" && !st.authenticated) {
      return { ok: false, why: st.status === "login_pending" ? "等待设备授权" : "尚未登录" };
    }
    return { ok: true, why: null };
  };

  const loginCodex = async () => {
    setLoginStarting(true);
    connectingCodex.current = true;
    setCliModel(""); setCliModels([]);
    try {
      await startCodexDeviceAuth(authHeaders());
      await refreshAvail();
    } catch (e) {
      connectingCodex.current = false;
      toast.error(e instanceof Error ? e.message : "Codex 登录启动失败");
    } finally {
      setLoginStarting(false);
    }
  };

  const providerOf = (id: string): ProviderId => aiModels.find((m) => m.id === id)?.provider ?? "openai-compatible";

  const pickApiModel = (id: string) => {
    const m = apiModels.find((x) => x.id === id);
    if (!m) return;
    setApiId(id);
    setModelName(id);
    setAvailableApiModels([id]);
    setBaseURL(PROVIDER_BASE[m.provider] || "");
  };

  const loadCliModels = async () => {
    setFetchingModels(true);
    try {
      const data = await refreshAvail();
      const codex = data?.clis.find((item) => item.kind === "codex");
      if (!codex?.models?.length) throw new Error("当前 Codex CLI 未公开可用模型列表，请使用默认模型");
      setCliModels(codex.models);
      setCliModel((current) => current && codex.models!.includes(current) ? current : codex.model || codex.models![0]);
      toast.success(`已获取 ${codex.models.length} 个可用模型`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "获取模型失败");
    } finally {
      setFetchingModels(false);
    }
  };

  const loadApiModels = async () => {
    if (!baseURL.trim() || !apiKey.trim()) {
      toast.error("请先填写 Base URL 和 API Key");
      return;
    }
    setFetchingModels(true);
    try {
      const models = await fetchApiModels(baseURL.trim(), apiKey.trim(), authHeaders());
      if (!models.length) throw new Error("当前端点没有返回可用模型");
      setAvailableApiModels(models);
      setModelName((current) => models.includes(current) ? current : models[0]);
      toast.success(`已获取 ${models.length} 个可用模型`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "获取模型失败");
    } finally {
      setFetchingModels(false);
    }
  };

  const saveApi = async () => {
    if (!baseURL.trim() || !apiKey.trim() || !modelName.trim()) {
      toast.error("请填完 Base URL、API Key、Model");
      return;
    }
    try { await saveLlm({ provider: providerOf(apiId), baseURL: baseURL.trim(), apiKey: apiKey.trim(), model: modelName.trim() }); }
    catch (e) { toast.error(e instanceof Error ? e.message : "配置保存失败"); return; }
    setStaleBlocked(null);   // 配置已换新 → 那条"原配置失效"的提示要收起来
    toast.success("已保存你的 AI 配置，全站「问 AI / 复盘」现在可用");
  };

  const saveSubscription = async () => {
    const m = subscriptionModels.find((x) => x.id === cliId);
    if (!m || m.comingSoon) {
      toast.error("请选择一个可用的订阅（暂不支持标「即将支持」的）");
      return;
    }
    const st = cliState(m);
    if (!st.ok) {
      toast.error(`「${m.name}」不可用：${st.why ?? "未知原因"}`);
      return;
    }
    const model = m.provider === "cli-codex" ? cliModel.trim() || codexStatus?.model || m.id : m.id;
    try { await saveLlm({ provider: m.provider, baseURL: "", apiKey: "", model }); }
    catch (e) { toast.error(e instanceof Error ? e.message : "配置保存失败"); return; }
    setStaleBlocked(null);
    setChoosingModel(false);
    toast.success(`已选「${m.name}」订阅，后续分析使用你的账号`);
  };

  const forget = async () => {
    try { await clearLlm(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "清除失败"); return; }
    setApiKey("");
    setCliId("");
    setStaleBlocked(null);   // 旧配置已被清掉，提示没有对象了
    toast.success("已清除 AI 配置");
  };

  const saveAccess = () => {
    const k = accessKey.trim();
    saveAccessKey(k);
    setAccessKey(k);
    toast.success(k ? "已保存后端访问密钥（存本地）" : "已清除后端访问密钥");
    void refreshAvail();
  };

  const codexModelPicker = <div>
    <label htmlFor="codex-model" className="mb-2 block text-sm font-medium">选择 Codex 模型</label>
    <div className="flex flex-col gap-2 sm:flex-row">
      <div className="relative min-w-0 flex-1">
        <select id="codex-model" value={cliModel} onChange={e => setCliModel(e.target.value)} className={`${SELECT} font-mono text-xs`}>
          <option value="">CLI 默认模型{codexStatus?.model ? `（${codexStatus.model}）` : ""}</option>
          {cliModels.map(model => <option key={model} value={model}>{model}</option>)}
        </select>
        <ChevronDown aria-hidden="true" className={SELECT_ICON} />
      </div>
      <button type="button" onClick={() => void loadCliModels()} disabled={fetchingModels} className={MODEL_BUTTON}>
        <RefreshCw aria-hidden="true" className={`h-4 w-4 ${fetchingModels ? "animate-spin" : ""}`} />
        {fetchingModels ? "正在获取…" : "获取模型"}
      </button>
    </div>
    <p className="mt-2 text-xs leading-6 text-muted-foreground">{cliModels.length ? "已读取当前订阅的模型目录。保存后，分析将使用你选择的模型。" : "暂未获取到模型目录，可以重试获取，或使用 CLI 默认模型。"}</p>
  </div>;

  return (
    <div>
      {choosingModel && <dialog ref={modelDialog} aria-labelledby="codex-connected-title" onCancel={() => setChoosingModel(false)}
        className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-border bg-card p-6 text-foreground shadow-2xl backdrop:bg-black/70">
        <ShieldCheck aria-hidden="true" className="mb-4 h-8 w-8 text-primary" />
        <h2 id="codex-connected-title" className="text-xl font-semibold">Codex 已连接</h2>
        <p className="mb-6 mt-2 text-sm text-muted-foreground">最后一步，为你的账号选择分析模型。</p>
        {codexModelPicker}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button className={MODEL_BUTTON} onClick={() => setChoosingModel(false)}>稍后选择</button>
          <button className="min-h-11 rounded-xl bg-primary px-4 font-semibold text-primary-foreground focus-visible:ring-2 focus-visible:ring-primary" onClick={saveSubscription}>保存并完成连接</button>
        </div>
      </dialog>}
      <div className="mb-6"><h2 className="text-xl font-semibold">AI 接入</h2><p className="mt-2 text-sm text-muted-foreground">配置一次，全站的「问 AI」「复盘」都能用你自己的模型</p></div>
      <AccountPanel refresh={refreshAvail} />

      <div className="mb-4 flex items-start gap-2 rounded-lg border border-success/25 bg-success/5 p-3 text-xs text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />
        <span>{sharedWebsite ? "AI 配置仅属于当前网站账号，不会使用站长或其他成员的额度。" : "API key 保存在本地浏览器，请求时由后端转发给模型服务。"} 所有分析由你的模型给出，本产品不校准。</span>
      </div>

      {/* 两种接入方式 */}
      {staleBlocked && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span>
            你之前选的那个 AI CLI <b className="text-foreground">已被禁用</b>（{staleBlocked}），原配置已自动失效，
            现在「问 AI」不可用。请在下面改选 <b className="text-foreground">Claude Code</b>（订阅接入）或填一个 API key。
          </span>
        </div>
      )}
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <GlassCard glow={mode === "subscription"} onClick={() => setMode("subscription")}
          className={mode === "subscription" ? "ring-1 ring-primary/40" : "opacity-80"}>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">订阅接入</h3>
            {mode === "subscription" && <Check className="ml-auto h-4 w-4 text-primary" />}
          </div>
          {}
          <p className="mt-1 text-xs text-muted-foreground">调后端运行环境中的 AI CLI（{allowedCliLabel}），用订阅额度，<b className="text-foreground">免 API key</b>。</p>
        </GlassCard>

        <GlassCard glow={mode === "api"} onClick={() => setMode("api")}
          className={mode === "api" ? "ring-1 ring-primary/40" : "opacity-80"}>
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">API 接入</h3>
            {mode === "api" && <Check className="ml-auto h-4 w-4 text-primary" />}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">粘贴 API key，支持 DeepSeek / 豆包 / MiniMax / OpenAI / OpenRouter / 任意兼容端点。<b className="text-foreground">现已可用。</b></p>
        </GlassCard>
      </div>

      <GlassCard>
        {mode === "subscription" ? (
          <div className="space-y-3 text-sm">
            <p className="text-xs text-muted-foreground">
              {sharedWebsite ? "在你的私人实例中登录 Codex，后续分析使用你自己的订阅额度。" : "选择本机已安装并登录的 CLI，使用你的订阅额度。"}<b className="text-foreground">不用填 key</b>。
            </p>
            {availState === "failed" && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span>
                  没能从后端确认哪些 CLI 可用（后端没起来？或需要填下面的访问密钥）。
                  订阅接入暂时不可选 —— 可以先用「API 接入」。
                </span>
              </div>
            )}
            <div className="grid gap-2 sm:grid-cols-2">
              {subscriptionModels.map((m) => {
                const on = cliId === m.id;
                const { ok, why } = cliState(m);
                const notInstalled = why === "本机未安装这个命令";
                const needsLogin = why === "尚未登录" || why === "等待设备授权";
                return (
                  <button key={m.id} disabled={!ok} onClick={() => setCliId(m.id)}
                    className={`flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                      !ok
                        ? "cursor-not-allowed border-border/50 opacity-40"
                        : on
                        ? "border-primary/50 bg-primary/10"
                        : "border-border hover:bg-muted/40"
                    }`}>
                    <Terminal className={`h-4 w-4 shrink-0 ${on ? "text-primary" : "text-muted-foreground"}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 font-medium">
                        {m.name}
                        {m.comingSoon && <span className="rounded bg-muted/60 px-1 py-0.5 text-[9px] text-muted-foreground">即将支持</span>}
                        {/* 「没装」和「被禁用」要分开说：一个去装就行，一个别想了 */}
                        {!ok && !m.comingSoon && (
                          availState !== "ready"
                            ? <span className="rounded bg-muted/60 px-1 py-0.5 text-[9px] text-muted-foreground"
                                title={why ?? undefined}>{availState === "failed" ? "无法确认" : "检测中"}</span>
                            : notInstalled
                            ? <span className="rounded bg-muted/60 px-1 py-0.5 text-[9px] text-muted-foreground"
                                title="服务端在本机 PATH 里没找到这个命令">未安装</span>
                            : needsLogin
                            ? <span className="rounded bg-primary/10 px-1 py-0.5 text-[9px] text-primary"
                                title={why ?? undefined}>待登录</span>
                            : <span className="rounded bg-danger/15 px-1 py-0.5 text-[9px] font-bold text-danger"
                                title={why ?? undefined}>⛔ 已禁用</span>
                        )}
                        {on && <Check className="h-3.5 w-3.5 text-primary" />}
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">{m.description}</div>
                    </div>
                  </button>
                );
              })}
            </div>
            {providerOf(cliId) === "cli-codex" && !choosingModel && codexModelPicker}
            {codexStatus?.allowed && codexStatus.installed && !codexStatus.authenticated && (
              <div className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => void loginCodex()}
                    disabled={loginStarting || codexStatus.status === "login_pending"}
                    className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-foreground disabled:opacity-50">
                    {loginStarting ? "正在启动…" : codexStatus.status === "login_pending" ? "等待授权…" : "登录 Codex"}
                  </button>
                  <span className="text-muted-foreground">{codexStatus.detail}</span>
                </div>
                {codexStatus.deviceAuth && (
                  <div role="status" className="mt-3 space-y-2">
                    <a href="https://auth.openai.com/codex/device" target="_blank" rel="noopener noreferrer"
                      className="text-primary underline">打开 Codex 官方授权页</a>
                    <p>输入一次性验证码：
                      <code className="ml-1 select-all font-mono text-base text-foreground">{codexStatus.deviceAuth.userCode}</code>
                    </p>
                    <p className="text-muted-foreground">授权完成后本页会自动检测，无需刷新。</p>
                  </div>
                )}
              </div>
            )}
            {}
            <div className="mt-2 flex items-start gap-2 rounded-lg border border-border bg-muted/20 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                <b>为什么部分 CLI 被禁用</b>：这些 CLI 以「自动批准」方式运行，
                会<b>不经询问</b>地读写文件、执行命令；而问 AI 时
                <b>页面上下文会原样进 prompt</b> —— 页面里那些抓来的
                外部新闻与研报原文，若夹带提示注入，就能驱动它动你的文件。
                Claude Code 被限制了文件与命令工具
                （<code className="text-[10px]">--disallowedTools</code>），
                <b>功能上完全够用</b>（问 AI 是一次性作答，不需要那些工具）。
                要放开某一个：给服务端设
                <code className="text-[10px]">VIBE_ALLOW_UNSAFE_CLI=qwen</code>（可逗号分隔），
                前端不用改。
              </span>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button onClick={saveSubscription} className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25">
                保存
              </button>
              {existing && (
                <button onClick={forget} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-4 w-4" /> 清除
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div>
              <label htmlFor="api-provider" className="mb-1.5 block text-xs font-medium text-muted-foreground">选择服务商</label>
              <div className="relative">
                <select id="api-provider" value={apiId} onChange={(e) => pickApiModel(e.target.value)} className={SELECT}>
                  {apiModels.map((m) => (
                    <option key={m.id} value={m.id}>{m.name} —— {m.description}</option>
                  ))}
                </select>
                <ChevronDown aria-hidden="true" className={SELECT_ICON} />
              </div>
            </div>

            <div>
              <label htmlFor="api-base-url" className="mb-1.5 block text-xs font-medium text-muted-foreground">Base URL</label>
              <input id="api-base-url" value={baseURL} onChange={(e) => setBaseURL(e.target.value)} placeholder="https://api.deepseek.com" className={INPUT} />
            </div>
            <div>
              <label htmlFor="api-model" className="mb-1.5 block text-xs font-medium text-muted-foreground">Model</label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <div className="relative min-w-0 flex-1">
                  <select id="api-model" value={modelName} onChange={(e) => setModelName(e.target.value)}
                    className={`${SELECT} font-mono text-xs`}>
                    {availableApiModels.map((model) => <option key={model} value={model}>{model}</option>)}
                  </select>
                  <ChevronDown aria-hidden="true" className={SELECT_ICON} />
                </div>
                <button type="button" onClick={() => void loadApiModels()} disabled={fetchingModels} className={MODEL_BUTTON}>
                  {fetchingModels ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden="true" className="h-4 w-4" />}
                  获取模型
                </button>
              </div>
            </div>
            <div>
              <label htmlFor="api-key" className="mb-1.5 block text-xs font-medium text-muted-foreground">API Key</label>
              <input id="api-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-…"
                autoComplete="off" className={INPUT} />
            </div>

            <div className="flex items-center gap-2">
              <button onClick={saveApi} className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25">
                {sharedWebsite ? "保存到我的账号" : "保存（存本地）"}
              </button>
              {existing && (
                <button onClick={forget} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-4 w-4" /> 清除
                </button>
              )}
            </div>
          </div>
        )}
      </GlassCard>

      {/* 后端访问密钥：仅当后端部署时设置了 VR_API_KEY（公网防蹭用）才需要填 */}
      {!sharedWebsite && <GlassCard className="mt-4">
        <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
          <KeyRound className="h-4 w-4 text-primary" /> 后端访问密钥（可选）
        </h3>
        <p className="mb-3 text-xs text-muted-foreground">
          仅当后端部署时设置了 <code className="rounded bg-muted/50 px-1">VR_API_KEY</code>（公网部署防蹭用）才需要填，填后端同一个值；
          本机自用没设鉴权就留空。同样只存本地浏览器。
        </p>
        <div className="flex items-center gap-2">
          <input type="password" value={accessKey} onChange={(e) => setAccessKey(e.target.value)} placeholder="与后端 VR_API_KEY 保持一致"
            className="flex-1 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          <button onClick={saveAccess} className="rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/25">
            保存
          </button>
        </div>
      </GlassCard>}
    </div>
  );
}
