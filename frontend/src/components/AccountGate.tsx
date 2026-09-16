import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { accountRequest, initializeAccount, sharedWebsite, websiteUser } from "@/lib/account";
import { primeCliAvailability } from "@/lib/ai-models";
import { authHeaders } from "@/lib/api";
import { ArrowRight, CandlestickChart, LockKeyhole, Users } from "lucide-react";

export function AccountGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "login" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [activate, setActivate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");

  useEffect(() => {
    initializeAccount().then(() => {
      if (sharedWebsite && !websiteUser) setState("login");
      else { void primeCliAvailability(authHeaders()); setState("ready"); }
    }).catch((e) => { setError(e.message); setState("error"); });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await accountRequest(`/api/account/${activate ? "activate" : "login"}`, "POST", { username, password, invite });
      localStorage.setItem("vibe-account-changed", String(Date.now()));
      window.location.reload();
    } catch (e) { setError(e instanceof Error ? e.message : "登录失败"); setBusy(false); }
  }

  if (state === "ready") return children;
  const input = "mt-2 min-h-12 w-full rounded-xl border border-border bg-background px-4 text-base transition-colors hover:border-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
  return <main className="login-page text-foreground">
    <header className="login-brand">
      <span className="login-mark"><CandlestickChart aria-hidden="true" className="h-7 w-7" /></span>
      <span className="text-xl font-bold tracking-tight">Vibe-Astock</span>
      <span className="ml-auto hidden text-xs text-muted-foreground sm:block">A 股短线 · 共享投研</span>
    </header>
    <div className="login-layout">
      <section className="login-story" aria-label="共享投研介绍">
        <p className="mb-5 flex items-center gap-2 text-sm text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-primary" />从收盘开始，让判断更清晰</p>
        <h1 className="login-headline">看清盘面，<br />再做决定。</h1>
        <p className="mt-6 max-w-sm text-base leading-8 text-muted-foreground">把市场线索沉淀为复盘，与朋友分享洞察。<br className="hidden sm:block" />你的交易节奏，留在自己的空间。</p>
        <div className="login-chart" aria-hidden="true">
          <svg viewBox="0 0 560 210" fill="none">
            {[45, 95, 145, 195].map(y => <path key={y} d={`M0 ${y}H560`} className="login-grid" />)}
            {[20, 90, 160, 230, 300, 370, 440, 510].map(x => <path key={x} d={`M${x} 15V205`} className="login-grid" />)}
            {[[30, 125, 34], [68, 112, 29], [106, 120, 42], [144, 100, 36], [182, 82, 43], [220, 99, 28], [258, 68, 37], [296, 53, 40], [334, 70, 30], [372, 50, 35], [410, 28, 46], [448, 43, 26], [486, 22, 31]].map(([x, y, h], i) => <g key={x} className={`login-candle ${i % 3 === 2 ? "login-candle-muted" : ""}`} style={{ animationDelay: `${i * 65}ms` }}>
              <path d={`M${x + 6} ${y - 13}V${y + h + 12}`} stroke="currentColor" strokeWidth="1.5" />
              <rect x={x} y={y} width="12" height={h} rx="2" fill="currentColor" />
            </g>)}
            <path className="login-trend" pathLength="1" d="M0 180C65 179 74 186 120 163S181 158 225 143 280 137 322 118 374 122 408 103 491 93 548 64" />
          </svg>
          <div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>市场情绪 · 题材主线 · 交易节奏</span><span>复盘，让线索连起来</span></div>
        </div>
        <div className="login-principles">
          <p><Users aria-hidden="true" className="h-4 w-4 text-primary" />研究成果，共同阅读</p>
          <p><LockKeyhole aria-hidden="true" className="h-4 w-4 text-primary" />个人交易，独立记录</p>
        </div>
      </section>
      <section className="login-form-panel" aria-label={activate ? "激活网站账号" : "登录网站"}>
      <p className="mb-3 text-sm text-primary">{activate ? "受邀加入" : "欢迎回来"}</p>
      <h2 className="text-3xl font-semibold tracking-tight">{activate ? "开启你的投研空间" : "进入你的投研空间"}</h2>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{activate ? "输入朋友发来的账号与邀请码，设置自己的密码。" : "登录后即可阅读共享复盘，无需先连接 AI。"}</p>
      {state === "loading" && <p role="status" className="mt-6">正在确认登录状态…</p>}
      {state === "error" && <button className={`${input} mt-6`} onClick={() => window.location.reload()}>重新连接</button>}
      {state === "login" && <form onSubmit={submit} className="mt-8 space-y-5" aria-describedby={error ? "login-error" : undefined}>
        <label className="block text-sm font-medium">网站账号<input className={input} autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="输入你的网站账号" value={username} onChange={e => setUsername(e.target.value)} required maxLength={32} /></label>
        {activate && <label className="block text-sm">一次性邀请码<input className={input} autoComplete="off" value={invite} onChange={e => setInvite(e.target.value)} required maxLength={128} /></label>}
        <label className="block text-sm">{activate ? "设置密码（至少 12 个字符）" : "密码"}<input className={input} type="password" autoComplete={activate ? "new-password" : "current-password"} value={password} onChange={e => setPassword(e.target.value)} required minLength={activate ? 12 : 1} maxLength={256} /></label>
        <button disabled={busy} className="login-submit flex min-h-12 w-full items-center justify-between rounded-xl bg-primary px-4 font-semibold text-primary-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"><span>{busy ? "正在处理…" : activate ? "激活账号" : "登录"}</span><ArrowRight aria-hidden="true" className="h-4 w-4" /></button>
        <button type="button" disabled={busy} className="min-h-11 w-full rounded-lg text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" onClick={() => { setActivate(!activate); setPassword(""); setError(""); }}>{activate ? "已有账号，去登录" : "首次使用，使用邀请激活"}</button>
      </form>}
      {error && <p id="login-error" role="alert" className="mt-4 text-sm text-danger">{error}</p>}
      <p className="mt-7 border-t border-border pt-5 text-xs leading-6 text-muted-foreground">需要发起 AI 分析时，再连接你自己的订阅或 API。<br />自选、盯盘、持仓和交易日志按账号独立保存。</p>
      </section>
    </div>
    <footer className="login-footer"><span>共享洞察，独立判断。</span><span>AI 辅助研究 · 非投资建议</span></footer>
  </main>;
}
