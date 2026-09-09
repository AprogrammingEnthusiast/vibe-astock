import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Moon, Sun, ChevronsLeft, ChevronsRight, CandlestickChart, Cog, Swords,
  Activity, Flame, CalendarRange, Bot, NotebookPen, TrendingDown,
  Microscope, Sunrise, Eye, Briefcase, Star, LineChart, Radio, LogOut } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { loadLlm } from "@/lib/llm";
import { websiteUser, logoutWebsite } from "@/lib/account";
import { toast } from "sonner";

import { useDarkMode } from "@/hooks/useDarkMode";

const APP_VERSION = "v0.2.1";

// 产品主体 = 复盘看板：打开就看清今天的短线情绪。
// 复盘看板本身由 agent 驱动（带 🤖 角标），其余是它的分项数据。
const REVIEW_NAV = [
  { to: "/agent/review", icon: Swords, label: "复盘看板", agent: true },
  { to: "/daily-review", icon: Activity, label: "盘面数据" },
  { to: "/first-board", icon: Flame, label: "首板分析" },
  { to: "/heat", icon: CalendarRange, label: "近5天热度" },
  { to: "/backtest", icon: TrendingDown, label: "涨停样本统计" },
];

// 个人交易记录。⛔ 这一组的数据只在本机流动，不接入任何 AI prompt。
const JOURNAL_NAV = [
  { to: "/journal", icon: NotebookPen, label: "交易日志" },
];

// 盯盘与自选：看当下与自己关心的标的
const WATCH_NAV = [
  { to: "/watch", icon: Eye, label: "盯盘" },
  { to: "/portfolio", icon: Briefcase, label: "持仓股" },
  { to: "/watchlist", icon: Star, label: "自选股" },
  { to: "/stock-data", icon: LineChart, label: "个股数据" },
  { to: "/intel", icon: Radio, label: "资讯雷达" },
];

// 按需跑的单股 agent（与每日复盘不同：它是你点一次跑一次）
const AGENT_NAV = [
  { to: "/agent/intraday", icon: Sunrise, label: "盘中核验" },
  { to: "/agent/deepdive", icon: Microscope, label: "个股深挖", agent: true },
];

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("va-sidebar") === "collapsed");
  const [llm, setLlm] = useState(loadLlm);
  const [loggingOut, setLoggingOut] = useState(false);
  const inSettings = pathname === "/settings" || pathname.startsWith("/settings/");
  const settingsLink = <Link to="/settings" aria-label="设置" title="设置" aria-current={inSettings ? "page" : undefined}
    className={cn("flex min-h-11 items-center justify-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
      collapsed ? "w-10 px-0" : "flex-1 justify-start",
      inSettings ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
    <Cog aria-hidden="true" className="h-4 w-4 shrink-0" />{!collapsed && "设置"}
  </Link>;

  const logoutButton = websiteUser && <button type="button" aria-label="退出登录" title={`退出登录 · ${websiteUser.username}`} disabled={loggingOut}
            onClick={async () => {
              setLoggingOut(true);
              try { await logoutWebsite(); }
              catch (e) { toast.error(e instanceof Error ? e.message : "退出失败，请重试"); setLoggingOut(false); }
            }}
            className={cn("flex min-h-11 items-center rounded-lg text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50", "w-9 shrink-0 justify-center")}>
            <LogOut aria-hidden="true" className="h-4 w-4 shrink-0" />
          </button>;

  useEffect(() => {
    localStorage.setItem("va-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  useEffect(() => {
    const refresh = () => setLlm(loadLlm());
    window.addEventListener("llm-config-change", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("llm-config-change", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const item = ({ to, icon: Icon, label }: { to: string; icon: LucideIcon; label: string }, agent = false) => {
    const active = pathname === to;
    return (
      <Link
        key={to}
        to={to}
        title={collapsed ? label : undefined}
        className={cn(
          "flex items-center rounded-lg text-sm transition-colors",
          collapsed ? "justify-center p-2.5" : "gap-2.5 px-3 py-2.5",
          active
            ? "bg-primary/15 font-medium text-primary shadow-glow"
            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
        )}
      >
        {agent ? (
          <span className="relative flex shrink-0">
            <Icon className="h-4 w-4" />
            <Bot className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 rounded-full bg-background text-primary" />
          </span>
        ) : (
          <Icon className="h-4 w-4 shrink-0" />
        )}
        {!collapsed && label}
      </Link>
    );
  };

  const groupLabel = (text: string) =>
    !collapsed && (
      <div className="mb-1 mt-3 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60 first:mt-0">{text}</div>
    );

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className={cn(
        "glass z-10 m-2 flex shrink-0 flex-col rounded-2xl transition-all duration-200",
        collapsed ? "w-14" : "w-60",
      )}>
        {/* Brand */}
        <div className={cn("border-b border-border/50", collapsed ? "flex justify-center p-3" : "p-4")}>
          <Link to="/agent/review" className={cn("flex items-center", collapsed ? "justify-center" : "gap-2")}>
            <CandlestickChart className="h-6 w-6 shrink-0 text-primary text-glow" />
            {!collapsed && <span className="text-lg font-extrabold tracking-tight">Vibe-<span className="text-primary">Astock</span></span>}
          </Link>
          {!collapsed && (
            <>
              <p className="mt-1 text-[11px] text-muted-foreground">{websiteUser ? `公共复盘 · ${websiteUser.username} 的私人空间` : "A 股短线复盘"}</p>
              <p title={llm?.model} className="mt-2 flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
                <Bot aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-primary" />
                <span className="shrink-0">{llm ? "已接入 AI" : "尚未接入 AI"}</span>
                {llm && <span className="truncate font-mono text-foreground/80">· {llm.model}</span>}
              </p>
            </>
          )}
        </div>

        {/* Nav */}
        <nav className={cn("flex-1 space-y-0.5 overflow-auto", collapsed ? "p-1.5" : "p-2.5")}>
          {groupLabel("复盘")}
          {REVIEW_NAV.map((n) => item(n, "agent" in n && n.agent))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("盯盘与自选")}
          {WATCH_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("按需分析")}
          {AGENT_NAV.map((n) => item(n, "agent" in n && n.agent))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("我的交易")}
          {JOURNAL_NAV.map((n) => item(n))}

        </nav>

        {/* Footer */}
        <div className={cn("border-t border-border/50", collapsed ? "flex flex-col items-center gap-2 p-2" : "space-y-2 p-3")}>
          {collapsed ? (
            <>
              {settingsLink}
              <button onClick={toggle} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={dark ? "亮色" : "暗色"}>
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              {logoutButton}
              <button onClick={() => setCollapsed(false)} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="展开">
                <ChevronsRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                {settingsLink}
                <button onClick={toggle} aria-label={dark ? "切换到亮色" : "切换到暗色"} title={dark ? "亮色" : "暗色"} className="flex min-h-11 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                </button>
                {logoutButton}
                <div className="flex items-center gap-2">
                  <button onClick={() => setCollapsed(true)} className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground" title="收起">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground/60">{APP_VERSION} · AI 生成 · 仅供参考 · 非投资建议</p>
            </>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
