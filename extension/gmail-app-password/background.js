// HX-Email Gmail 应用专用密码助手 — service worker（MV3）
// 职责：content script 无法直接调用 chrome.tabs，所有“打开页面”统一经由此处转发。

const DEFAULT_BASE_URL = "http://localhost:8000";

function openTab(url) {
  chrome.tabs.create({ url });
}

async function settings() {
  const stored = await chrome.storage.sync.get({ baseUrl: DEFAULT_BASE_URL, appName: "HX-Email" });
  return stored;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message.type !== "string") return;

  switch (message.type) {
    case "hx-open-url":
      openTab(String(message.url || ""));
      sendResponse({ ok: true });
      break;

    // 生成成功后：记录最近一次结果 + 可选自动打开 HX-Email
    case "hx-generated":
      chrome.storage.local.set({ lastGenerated: message.payload || {} });
      if (message.payload && message.payload.openHxEmail) {
        settings().then((cfg) => {
          const base = String(cfg.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "");
          if (base) openTab(base);
        });
      }
      sendResponse({ ok: true });
      break;

    case "hx-get-settings":
      settings().then((cfg) => sendResponse(cfg));
      return true; // async response

    default:
      break;
  }
  return undefined;
});
