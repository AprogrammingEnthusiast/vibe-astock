import { apiUrl } from "./base";

export interface WebsiteUser { id: string; username: string; admin: boolean; }
export let websiteUser: WebsiteUser | null = null;
export let sharedWebsite = false;

export function accountKey(key: string): string {
  return sharedWebsite ? `${key}:account:${websiteUser?.id ?? "signed-out"}` : key;
}

// Every existing API client gets the same CSRF and account binding, including streams.
const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  const apiPath = new URL(apiUrl("/api/"), window.location.href).pathname;
  if (url.origin !== window.location.origin || !url.pathname.startsWith(apiPath)) return originalFetch(input, init);
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  headers.set("X-Vibe-Request", "1");
  if (websiteUser) headers.set("X-Vibe-Account", websiteUser.id);
  const response = await originalFetch(input, { ...init, headers });
  if (sharedWebsite && websiteUser && response.status === 401) {
    window.location.reload();
    throw new Error("网站登录已过期，请重新登录");
  }
  return response;
};

export async function accountRequest(path: string, method = "GET", body?: unknown) {
  const response = await fetch(apiUrl(path), {
    method, headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.detail || value.error || "请求失败，请重试");
  return value;
}

export async function initializeAccount() {
  const response = await fetch(apiUrl("/api/account/me"));
  if (response.status === 404) return; // Existing single-user deployment.
  if (!response.ok) throw new Error("无法确认网站登录状态，请重试");
  const data = await response.json();
  sharedWebsite = data.shared === true;
  websiteUser = data.user;
  if (!websiteUser) return;
  localStorage.setItem(accountKey("vr-watchlist"), JSON.stringify(data.watchlist ?? []));
  const profile = await accountRequest("/api/personal/llm");
  const connection = await accountRequest("/api/personal/agent-connection");
  if (connection.llm) localStorage.setItem(accountKey("astock-agent-connection"), JSON.stringify(connection.llm));
  else localStorage.removeItem(accountKey("astock-agent-connection"));
  if (profile.llm) localStorage.setItem(accountKey("vr-llm"), JSON.stringify(profile.llm));
  else localStorage.removeItem(accountKey("vr-llm"));
}

export async function logoutWebsite() {
  await accountRequest("/api/account/logout", "POST");
  localStorage.removeItem(accountKey("vr-llm"));
  localStorage.removeItem(accountKey("astock-agent-connection"));
  sessionStorage.clear();
  localStorage.setItem("vibe-account-changed", String(Date.now()));
  window.location.reload();
}

window.addEventListener("storage", (event) => {
  if (sharedWebsite && event.key === "vibe-account-changed") window.location.reload();
});
