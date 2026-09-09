import { toast } from "sonner";
import { accountRequest, sharedWebsite, websiteUser, logoutWebsite, accountKey } from "@/lib/account";
import { saveWatch } from "@/lib/watchlist";
import { clearLlm } from "@/lib/llm";

export function AccountPanel({ refresh }: { refresh: () => Promise<unknown> }) {
  if (!sharedWebsite) return null;
  const button = "min-h-11 rounded-lg border border-border px-3 text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-primary";
  return <section className="mb-4 rounded-xl border border-border bg-card p-4 text-sm" aria-label="网站账户">
    <p>当前网站账号：<b>{websiteUser?.username}</b> · 自选、盯盘和交易日志仅你可见</p>
    <p className="mt-2 text-xs leading-6 text-muted-foreground">阅读公共复盘不调用 AI。订阅和 API 凭证保存在你的私人服务实例中，由站点服务器托管；你发起分析时使用自己的额度。</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <button className={button} onClick={() => void logoutWebsite().catch(e => toast.error(e.message))}>退出网站账号</button>
      <button className={button} onClick={async () => {
        try { await accountRequest("/api/cli/codex/logout", "POST"); await clearLlm(); await refresh(); window.location.reload(); }
        catch (e) { toast.error(e instanceof Error ? e.message : "断开失败"); }
      }}>断开我的 Codex</button>
      {websiteUser?.admin && <button className={button} onClick={async () => {
        try {
          const old = JSON.parse(localStorage.getItem("vr-watchlist") || "[]");
          const current = JSON.parse(localStorage.getItem(accountKey("vr-watchlist")) || "[]");
          await saveWatch([...new Set<string>([...current, ...old])].filter(c => /^[0-9]{6}$/.test(c)));
          for (const key of ["vr-notes", "vr-deepdive"]) {
            const legacy = localStorage.getItem(key);
            if (legacy && !localStorage.getItem(accountKey(key))) localStorage.setItem(accountKey(key), legacy);
          }
          toast.success("已导入这台浏览器原有的自选和研究记录");
        } catch { toast.error("旧数据格式异常，未完成导入"); }
      }}>导入原有浏览器自选和记录</button>}
    </div>
  </section>;
}
