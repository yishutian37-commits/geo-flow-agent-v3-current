import { registerTool, getTabId, type ToolExecutor } from "./index.js";

const screenshotTool: ToolExecutor = {
  name: "screenshot",
  async execute(params, ctx) {
    const tabId = await getTabId(params, ctx);
    await ctx.cdp.attach(tabId);

    const format = (params.format as string) || "png";
    const fullPage = params.fullPage as boolean | undefined;
    const selector = params.selector as string | undefined;
    let clip:
      | { x: number; y: number; width: number; height: number; scale: number }
      | undefined;
    let shouldRestoreSelector = false;

    if (selector) {
      const escapedSelector = JSON.stringify(selector);
      const selectorResult = await ctx.cdp.send<{ result?: { value?: string } }>("Runtime.evaluate", {
        returnByValue: true,
        expression: `
(() => {
  const selector = ${escapedSelector};
  const el = document.querySelector(selector);
  if (!el) return JSON.stringify({ ok: false, error: 'selector not found' });
  const rectBefore = el.getBoundingClientRect();
  if (rectBefore.width <= 0 || rectBefore.height <= 0) {
    return JSON.stringify({ ok: false, error: 'selector invisible' });
  }
  const previous = {
    height: el.style.height,
    maxHeight: el.style.maxHeight,
    overflow: el.style.overflow,
    overflowY: el.style.overflowY,
    scrollTop: el.scrollTop,
  };
  el.__qwebScreenshotRestore = previous;
  try { el.scrollTop = 0; } catch (error) {}
  const scrollHeight = Math.max(el.scrollHeight || 0, rectBefore.height || 0);
  if (scrollHeight > rectBefore.height + 10) {
    el.style.maxHeight = 'none';
    el.style.height = Math.min(scrollHeight, 18000) + 'px';
    el.style.overflow = 'visible';
    el.style.overflowY = 'visible';
  }
  el.scrollIntoView({ block: 'start', inline: 'nearest' });
  const rect = el.getBoundingClientRect();
  return JSON.stringify({
    ok: true,
    x: rect.left + window.scrollX,
    y: rect.top + window.scrollY,
    width: rect.width,
    height: Math.min(Math.max(rect.height, scrollHeight, 1), 18000),
  });
})()
        `,
      });
      const rect = JSON.parse(selectorResult.result?.value || "null") as
        | { ok?: boolean; error?: string; x: number; y: number; width: number; height: number }
        | null;
      if (!rect?.ok || rect.width <= 0 || rect.height <= 0) {
        throw new Error(`screenshot selector not found or invisible: ${selector}`);
      }
      shouldRestoreSelector = true;
      clip = {
        x: Math.max(0, rect.x),
        y: Math.max(0, rect.y),
        width: Math.max(1, rect.width),
        height: Math.max(1, rect.height),
        scale: 1,
      };
    } else if (fullPage) {
      const metrics = await ctx.cdp.send<{
        contentSize?: { x: number; y: number; width: number; height: number };
      }>("Page.getLayoutMetrics", {});
      const contentSize = metrics.contentSize;
      if (contentSize?.width && contentSize?.height) {
        clip = {
          x: contentSize.x || 0,
          y: contentSize.y || 0,
          width: contentSize.width,
          height: contentSize.height,
          scale: 1,
        };
      }
    }

    let result: { data: string };
    try {
      result = await ctx.cdp.send<{ data: string }>("Page.captureScreenshot", {
        format: format as "png" | "jpeg" | "webp",
        quality: params.quality as number | undefined,
        captureBeyondViewport: Boolean(fullPage || selector),
        fromSurface: true,
        clip,
      });
    } finally {
      if (selector && shouldRestoreSelector) {
        const escapedSelector = JSON.stringify(selector);
        await ctx.cdp.send("Runtime.evaluate", {
          expression: `
(() => {
  const el = document.querySelector(${escapedSelector});
  const previous = el && el.__qwebScreenshotRestore;
  if (!el || !previous) return;
  el.style.height = previous.height || '';
  el.style.maxHeight = previous.maxHeight || '';
  el.style.overflow = previous.overflow || '';
  el.style.overflowY = previous.overflowY || '';
  try { el.scrollTop = previous.scrollTop || 0; } catch (error) {}
  delete el.__qwebScreenshotRestore;
})()
          `,
        }).catch(() => undefined);
      }
    }

    return { success: true, data: result.data };
  },
};

registerTool(screenshotTool);
