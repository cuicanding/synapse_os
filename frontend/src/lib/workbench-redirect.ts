// ─── 工作台跳转 ────────────────────────────────────────────────────────
import { writable } from "svelte/store";

export const workbenchRedirect = writable<{
  channelId: string | null;
  prefillMessage: string;
} | null>(null);
