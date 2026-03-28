<script lang="ts">
  import { marked } from "marked";
  import DOMPurify from "dompurify";

  export let title: string;
  export let content: string;
  export let initialOpen: boolean = false;
  export let accentColor: "cyan" | "amber" | "violet" | "green" = "cyan";

  let isOpen = initialOpen;

  marked.setOptions({ breaks: true, gfm: true });

  function renderMarkdown(text: string): string {
    const raw = marked.parse(text) as string;
    return DOMPurify.sanitize(raw);
  }

  const accentStyles: Record<string, string> = {
    cyan:   "border-cyber-cyan/20 text-cyber-cyan/70",
    amber:  "border-amber-500/20 text-amber-400/70",
    violet: "border-cyber-violet/20 text-cyber-violet/70",
    green:  "border-cyber-green/20 text-cyber-green/70",
  };

  const bgStyles: Record<string, string> = {
    cyan:   "bg-cyber-cyan/5",
    amber:  "bg-amber-500/5",
    violet: "bg-cyber-violet/5",
    green:  "bg-cyber-green/5",
  };
</script>

<div class="rounded-lg border {accentStyles[accentColor]} overflow-hidden">
  <!-- Toggle header -->
  <button
    class="w-full flex items-center justify-between px-3 py-2 {bgStyles[accentColor]} hover:brightness-110 transition-all text-left"
    on:click={() => (isOpen = !isOpen)}
  >
    <span class="text-xs font-mono {accentStyles[accentColor]}">{title}</span>
    <span class="text-xs font-mono {accentStyles[accentColor]} transition-transform duration-200 {isOpen ? 'rotate-90' : ''}">▶</span>
  </button>

  <!-- Collapsible content -->
  {#if isOpen}
    <div class="px-3 py-3 {bgStyles[accentColor]} border-t {accentStyles[accentColor]} markdown-body">
      {@html renderMarkdown(content)}
    </div>
  {/if}
</div>
