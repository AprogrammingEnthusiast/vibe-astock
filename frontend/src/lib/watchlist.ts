import { accountKey, accountRequest, sharedWebsite } from "./account";
// 自选随网站账号保存；单人部署仍使用本地存储。
// 行情复用 /api/quote；复盘时把关注股行情一并喂给用户自己的 AI。

const KEY = "vr-watchlist";

export function loadWatch(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(accountKey(KEY)) || "[]");
    return Array.isArray(v) ? v.filter((c) => /^\d{6}$/.test(c)) : [];
  } catch {
    return [];
  }
}

export async function saveWatch(codes: string[]) {
  if (sharedWebsite) await accountRequest("/api/account/watchlist", "PUT", { codes });
  localStorage.setItem(accountKey(KEY), JSON.stringify(codes));
}

// 从任意文本里抽取 6 位 A 股代码（逗号 / 空格 / 换行 / 顿号分隔都行，方便一次粘贴一串）。
export function parseCodes(raw: string): string[] {
  const tokens = raw.split(/[^\d]+/).filter(Boolean);
  return Array.from(new Set(tokens.filter((t) => /^\d{6}$/.test(t))));
}

// 把用户输入的一串代码并入已有自选，返回去重后的新列表 + 实际新增数量。
export function addCodes(existing: string[], raw: string): { next: string[]; added: number } {
  const incoming = parseCodes(raw).filter((c) => !existing.includes(c));
  return { next: [...existing, ...incoming], added: incoming.length };
}
