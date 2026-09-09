import { onMounted, onActivated, onDeactivated, onBeforeUnmount, ref } from "vue";

/** Measure the remaining shell content area, not the full browser height. */
export function useEmbeddedViewport() {
  const panel = ref<HTMLElement>();
  const panelHeight = ref("calc(100dvh - 180px)");
  let observer: ResizeObserver | undefined;
  let frame = 0;
  let listening = false;
  function measure() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (!panel.value?.isConnected || !panel.value.getClientRects().length) return;
      const top = panel.value.getBoundingClientRect().top;
      let bottom = window.visualViewport ? window.visualViewport.height + window.visualViewport.offsetTop : window.innerHeight;
      let parent = panel.value.parentElement;
      while (parent && parent !== document.body) {
        const style = getComputedStyle(parent);
        const rect = parent.getBoundingClientRect();
        if (parent.matches("#app-scroll-main, #app-content, .el-scrollbar__wrap, main") && /(auto|scroll)/.test(style.overflowY) && rect.bottom > top + 180) bottom = Math.min(bottom, rect.bottom);
        parent = parent.parentElement;
      }
      const height = `${Math.max(180, Math.floor(bottom - Math.max(0, top) - 8))}px`;
      if (height !== panelHeight.value) panelHeight.value = height;
    });
  }
  function stop() {
    listening = false; observer?.disconnect(); observer = undefined; cancelAnimationFrame(frame);
    window.removeEventListener("resize", measure); window.visualViewport?.removeEventListener("resize", measure);
  }
  function start() {
    if (listening) return;
    listening = true; window.addEventListener("resize", measure); window.visualViewport?.addEventListener("resize", measure);
    observer = new ResizeObserver(measure);
    let parent = panel.value?.parentElement;
    while (parent && parent !== document.body) { observer.observe(parent); parent = parent.parentElement; }
    measure();
  }
  onMounted(start); onActivated(start); onDeactivated(stop); onBeforeUnmount(stop);
  return { panel, panelHeight };
}

export function openService(url: string) {
  if (!url || url.startsWith("//") || /[\\\x00-\x1f\x7f]/.test(url)) return;
  try {
    const target = new URL(url, window.location.origin);
    if (!["http:", "https:"].includes(target.protocol) || target.username || target.password) return;
    window.open(target.href, "_blank", "noopener,noreferrer");
  } catch { /* Invalid service URLs are rejected, never executed. */ }
}
