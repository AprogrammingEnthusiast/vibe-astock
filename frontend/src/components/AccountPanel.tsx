import { toast } from "sonner";
import { useRef, useState, type FormEvent } from "react";
import { accountRequest, sharedWebsite, websiteUser, logoutWebsite, accountKey } from "@/lib/account";
import { saveWatch } from "@/lib/watchlist";


export function AccountPanel({ refresh }: { refresh: () => Promise<unknown> }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const [changed, setChanged] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    if (newPassword !== confirmation) {
      setError("两次输入的新密码不一致");
      return;
    }
    submitting.current = true;
    setSaving(true);
    try {
      await accountRequest("/api/account/password", "PUT", {
        current_password: currentPassword, new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setChanged(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改失败，请重试");
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  if (!sharedWebsite) return null;
  const button = "min-h-11 rounded-lg border border-border px-3 text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-primary";
  const input = "mt-1 min-h-11 w-full rounded-lg border border-border bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
  return <section className="mb-4 rounded-xl border border-border bg-card p-4 text-sm" aria-label="网站账户">
    <p>当前网站账号：<b>{websiteUser?.username}</b> · 自选、盯盘和交易日志仅你可见</p>
    <p className="mt-2 text-xs leading-6 text-muted-foreground">阅读公共复盘不调用 AI。订阅和 API 凭证保存在本人账号空间中，由站点服务器托管；你发起分析时使用自己的额度。</p>
    <section className="mt-3 rounded-lg border border-border p-3" aria-label="修改密码">
      <h2 className="py-1 font-medium">修改密码</h2>
      {changed ? <div className="mt-3 space-y-3">
        <p role="status">密码已修改，所有设备的登录已失效，请重新登录。</p>
        <button type="button" className={button} onClick={() => void logoutWebsite().catch(e => setError(e.message))}>重新登录</button>
      </div> : <form onSubmit={changePassword} className="mt-3 max-w-md space-y-3" aria-label="修改密码">
        <p id="password-help" className="text-xs leading-6 text-muted-foreground">新密码须为 12–256 个字符。修改成功后，所有设备都需要重新登录。</p>
        <fieldset disabled={saving} className="space-y-3 disabled:opacity-60">
          <label className="block">当前密码<input type="password" name="current-password" autoComplete="current-password" required maxLength={256}
            value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} className={input} /></label>
          <label className="block">新密码<input type="password" name="new-password" autoComplete="new-password" required minLength={12} maxLength={256}
            aria-describedby="password-help" value={newPassword} onChange={e => setNewPassword(e.target.value)} className={input} /></label>
          <label className="block">确认新密码<input type="password" name="confirm-password" autoComplete="new-password" required minLength={12} maxLength={256}
            value={confirmation} onChange={e => setConfirmation(e.target.value)} className={input} /></label>
          <button type="submit" className={`${button} bg-primary text-primary-foreground hover:bg-primary/90 disabled:cursor-wait`}>
            {saving ? "正在修改…" : "确认修改密码"}
          </button>
        </fieldset>
      </form>}
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
    </section>
    <div className="mt-3 flex flex-wrap gap-3">
      <button className={button} onClick={() => void logoutWebsite().catch(e => toast.error(e.message))}>退出网站账号</button>
      <button className={button} onClick={async () => {
        try { await accountRequest("/api/review-agent/access/logout", "POST"); localStorage.removeItem(accountKey("astock-agent-connection")); await refresh(); window.location.reload(); }
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
