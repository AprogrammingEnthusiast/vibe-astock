import { accountKey } from "@/lib/account";
export interface HeadlineTranslationInput {
  id: string;
  title: string;
}

const CACHE_KEY = "vr-radar-title-translations-v1";
const CJK = /[\u3400-\u9fff]/;

export const hasChinese = (text: string) => CJK.test(text);

export function missingHeadlineTranslations(
  items: { title: string; zh?: string }[], cache: ReadonlyMap<string, string>, force = false,
): HeadlineTranslationInput[] {
  const unique = new Map<string, HeadlineTranslationInput>();
  items.forEach((item, index) => {
    if (!hasChinese(item.title) && (force || (!item.zh && !cache.has(item.title))) && !unique.has(item.title)) {
      unique.set(item.title, { id: String(index), title: item.title });
    }
  });
  return [...unique.values()];
}

export const displayedHeadlineTranslation = (
  item: { title: string; zh?: string }, cache: ReadonlyMap<string, string>,
) => cache.get(item.title) || item.zh || "";

export function splitHeadlineBatches(items: HeadlineTranslationInput[]): HeadlineTranslationInput[][] {
  const batches: HeadlineTranslationInput[][] = [];
  let batch: HeadlineTranslationInput[] = [];
  let chars = 0;
  for (const item of items) {
    const cost = item.id.length + item.title.length + 24;
    if (batch.length && (batch.length >= 16 || chars + cost > 2600)) {
      batches.push(batch);
      batch = [];
      chars = 0;
    }
    batch.push(item);
    chars += cost;
  }
  if (batch.length) batches.push(batch);
  return batches;
}

export function loadHeadlineTranslationCache(): Map<string, string> {
  try {
    const rows = JSON.parse(localStorage.getItem(accountKey(CACHE_KEY)) ?? "[]") as unknown;
    if (!Array.isArray(rows)) return new Map();
    return new Map(rows.slice(-1200).filter((row): row is [string, string] =>
      Array.isArray(row) && row.length === 2 && typeof row[0] === "string" &&
      typeof row[1] === "string" && hasChinese(row[1]),
    ));
  } catch {
    return new Map();
  }
}

export function saveHeadlineTranslationCache(cache: Map<string, string>): void {
  try {
    localStorage.setItem(accountKey(CACHE_KEY), JSON.stringify([...cache.entries()].slice(-1200)));
  } catch { /* 缓存不可用时仍展示原题 */ }
}
