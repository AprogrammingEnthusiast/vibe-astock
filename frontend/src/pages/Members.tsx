import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Copy, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { accountRequest, websiteUser } from "@/lib/account";

interface MembersData { members: { username: string; admin: boolean; status: string }[]; }

export function Members() {
  const [data, setData] = useState<MembersData | null>(null);
  const [username, setUsername] = useState("");
  const [invitation, setInvitation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    try { setData(await accountRequest("/api/admin/invitations")); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "无法读取成员，请重试"); }
  };
  useEffect(() => { if (websiteUser?.admin) void refresh(); }, []);
  if (!websiteUser?.admin) return <Navigate to="/settings" replace />;
  async function invite(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await accountRequest("/api/admin/invitations", "POST", { username });
      setInvitation(`邀请你加入 Vibe-Astock\n网站：${window.location.origin}${import.meta.env.BASE_URL}\n网站账号：${result.username}\n一次性邀请码：${result.invite}\n选择「首次使用，使用邀请激活」并设置自己的密码。阅读公共复盘无需 AI；使用 AI 请连接自己的订阅或 API。`);
      setUsername(""); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "邀请生成失败"); }
    finally { setBusy(false); }
  }
  const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50";
  return <div className="max-w-3xl">
    <div className="mb-6"><h2 className="text-xl font-semibold">邀请成员</h2><p className="mt-2 text-sm text-muted-foreground">一起看复盘，各自管理交易与 AI 账号</p></div>
    <section className="rounded-2xl border border-border bg-card p-5 sm:p-7" aria-label="发放邀请码">
      <UserPlus aria-hidden="true" className="mb-4 h-7 w-7 text-primary" />
      <h2 className="text-lg font-semibold">邀请一位朋友</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">为朋友设置一个网站账号，生成专属的一次性邀请码。朋友激活后，就能阅读共享复盘。</p>
      <form onSubmit={invite} className="mt-6">
        <label htmlFor="member-name" className="text-sm font-medium">朋友的网站账号</label>
        <div className="mt-2 flex flex-wrap gap-3">
          <input id="member-name" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={32}
            pattern="[a-z][a-z0-9_\-]{2,31}" autoComplete="off" autoCapitalize="none" spellCheck={false} aria-describedby="member-name-hint"
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-border bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" placeholder="例如 friend01" />
          <button disabled={busy || !data} className={`${button} bg-primary text-primary-foreground`}>
            <UserPlus aria-hidden="true" className="h-4 w-4" />{busy ? "正在生成…" : "生成邀请码"}
          </button>
        </div>
        <p id="member-name-hint" className="mt-2 text-xs leading-6 text-muted-foreground">3–32 位小写字母、数字、下划线或短横线，以字母开头。</p>
      </form>
      {!data && !error && <p className="mt-4 text-sm text-muted-foreground" role="status">正在读取成员列表…</p>}
      {error && <div className="mt-4" role="alert"><p className="text-sm text-danger">{error}</p><button className={`${button} mt-2 border border-border`} onClick={() => void refresh()}>刷新成员列表</button></div>}
      {invitation && <div className="mt-6 border-t border-border pt-5">
        <label htmlFor="invitation-text" className="text-sm font-semibold">邀请码已生成，请复制给对应朋友</label>
        <p className="mb-3 mt-1 text-xs leading-6 text-muted-foreground">邀请码只在此处显示一次，激活后失效。</p>
        <textarea id="invitation-text" readOnly value={invitation} rows={7} className="w-full resize-y rounded-xl border border-border bg-background p-3 font-mono text-xs leading-6 focus-visible:ring-2 focus-visible:ring-primary" />
        <button className={`${button} mt-3 border border-border hover:bg-muted`} onClick={async () => {
          try { await navigator.clipboard.writeText(invitation); toast.success("邀请已复制"); }
          catch { toast.error("无法自动复制，请选中上方邀请文字手动复制"); }
        }}><Copy aria-hidden="true" className="h-4 w-4" />复制邀请</button>
      </div>}
    </section>
    <section className="mt-7" aria-label="成员列表">
      <h2 className="mb-3 flex items-center gap-2 font-semibold"><Users aria-hidden="true" className="h-4 w-4" />网站成员</h2>
      <ul className="divide-y divide-border rounded-xl border border-border bg-card px-4">
        {data?.members.map(member => <li key={member.username} className="flex flex-wrap items-center justify-between gap-3 py-4 text-sm">
          <span className="break-all font-medium">{member.username}{member.admin && <span className="ml-2 text-xs text-muted-foreground">管理员</span>}</span>
          <span className={member.status === "active" ? "text-foreground" : "text-muted-foreground"}>{member.status === "active" ? "已加入" : "等待激活"}</span>
        </li>)}
      </ul>
    </section>
  </div>;
}
