import { NavLink, Outlet } from "react-router-dom";
import { Bot, UserPlus, UserRound } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { sharedWebsite, websiteUser } from "@/lib/account";
import { cn } from "@/lib/utils";

export function SettingsLayout() {
  const sections = [
    { to: "/settings", label: "AI 接入", icon: Bot, end: true },
    ...(sharedWebsite ? [{ to: "/settings/account", label: "账号", icon: UserRound, end: false }] : []),
    ...(websiteUser?.admin ? [{ to: "/settings/members", label: "邀请成员", icon: UserPlus, end: false }] : []),
  ];
  return <div>
    <PageHeader title="设置" subtitle="管理你的 AI 接入、账号与网站成员" />
    <div className="flex min-w-0 flex-col gap-6 lg:flex-row lg:gap-8">
      <nav aria-label="设置分类" className="flex shrink-0 flex-wrap gap-2 border-b border-border pb-4 lg:w-40 lg:flex-col lg:self-start lg:border-b-0 lg:pb-0">
        {sections.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end}
          className={({ isActive }) => cn("flex min-h-11 items-center gap-2.5 rounded-xl px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
          <Icon aria-hidden="true" className="h-4 w-4" />{label}
        </NavLink>)}
      </nav>
      <div className="min-w-0 flex-1"><Outlet /></div>
    </div>
  </div>;
}
