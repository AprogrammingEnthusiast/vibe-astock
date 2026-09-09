import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { SettingsLayout } from "@/components/layout/SettingsLayout";
import { AgentReview } from "@/pages/AgentReview";
import { DailyReview } from "@/pages/DailyReview";
import { FirstBoard } from "@/pages/FirstBoard";
import { AgentWeekly } from "@/pages/AgentWeekly";
import { Journal } from "@/pages/Journal";
import { Backtest } from "@/pages/Backtest";
import { DeepDive } from "@/pages/DeepDive";
import { Intraday } from "@/pages/Intraday";
import { DailyWatch } from "@/pages/DailyWatch";
import { Portfolio } from "@/pages/Portfolio";
import { Watchlist } from "@/pages/Watchlist";
import { StockData } from "@/pages/StockData";
import { Intel } from "@/pages/Intel";
import { Settings } from "@/pages/Settings";
import { Members } from "@/pages/Members";

// basename 跟着构建时的 --base 走，这样挂在子路径下内部跳转才不会掉回站点根目录
export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/agent/review" replace /> },
      { path: "/agent/review", element: <AgentReview /> },
      { path: "/daily-review", element: <DailyReview /> },
      { path: "/first-board", element: <FirstBoard /> },
      { path: "/heat", element: <AgentWeekly /> },
      { path: "/journal", element: <Journal /> },
      { path: "/backtest", element: <Backtest /> },
      { path: "/watch", element: <DailyWatch /> },
      { path: "/portfolio", element: <Portfolio /> },
      { path: "/watchlist", element: <Watchlist /> },
      { path: "/stock-data", element: <StockData /> },
      { path: "/intel", element: <Intel /> },
      { path: "/agent/intraday", element: <Intraday /> },
      { path: "/agent/deepdive", element: <DeepDive /> },
      { path: "/settings", element: <SettingsLayout />, children: [
        { index: true, element: <Settings /> },
        { path: "members", element: <Members /> },
      ] },
      { path: "/members", element: <Navigate to="/settings/members" replace /> },
      { path: "*", element: <Navigate to="/agent/review" replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL });
