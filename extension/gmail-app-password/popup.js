// HX-Email Gmail 应用专用密码助手 — popup 控制面板
(() => {
  "use strict";

  const URLS = {
    appPasswords: "https://myaccount.google.com/apppasswords?hx=auto",
    twoStep: "https://myaccount.google.com/signinoptions/two-step-verification?hx=auto",
    imap: "https://mail.google.com/mail/u/0/#settings/fwdandpop",
  };

  const $ = (id) => document.getElementById(id);

  function openUrl(url) {
    chrome.tabs.create({ url });
    window.close();
  }

  async function loadSettings() {
    const stored = await chrome.storage.sync.get({ baseUrl: "http://localhost:8000", appName: "HX-Email" });
    $("baseUrl").value = stored.baseUrl;
    $("appName").value = stored.appName;
  }

  function bindSettings() {
    const persist = () => {
      chrome.storage.sync.set({ baseUrl: $("baseUrl").value.trim(), appName: $("appName").value.trim() || "HX-Email" });
    };
    $("baseUrl").addEventListener("change", persist);
    $("appName").addEventListener("change", persist);
  }

  async function renderLastResult() {
    const { lastGenerated } = await chrome.storage.local.get({ lastGenerated: null });
    const box = $("lastResult");
    if (!lastGenerated || !lastGenerated.password) {
      box.innerHTML = '<div class="l">最近一次生成</div><div class="empty">还没有生成记录。</div>';
      $("copyLine").style.display = "none";
      return;
    }
    const line = lastGenerated.line || (lastGenerated.email ? `${lastGenerated.email}----${lastGenerated.password}` : lastGenerated.password);
    box.innerHTML = `
      <div class="l">最近一次生成（${lastGenerated.copied ? "已复制" : "未复制"}）</div>
      <div class="pwd">${escapeHtml(lastGenerated.password)}</div>
      <div class="line">${escapeHtml(line)}</div>
      <div class="time">${lastGenerated.at ? new Date(lastGenerated.at).toLocaleString() : ""}</div>
    `;
    const copyBtn = $("copyLine");
    copyBtn.style.display = "block";
    copyBtn.onclick = async () => {
      let ok = false;
      try {
        await navigator.clipboard.writeText(line);
        ok = true;
      } catch (_err) {
        ok = false;
      }
      copyBtn.textContent = ok ? "✓ 已复制" : "复制失败，请手动复制";
      if (ok) setTimeout(() => (copyBtn.textContent = "复制导入行（邮箱----密码）"), 1500);
    };
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }

  document.querySelector('[data-step="twostep"]').addEventListener("click", () => openUrl(URLS.twoStep));
  document.querySelector('[data-step="generate"]').addEventListener("click", () => openUrl(URLS.appPasswords));
  document.querySelector('[data-step="imap"]').addEventListener("click", () => openUrl(URLS.imap));

  loadSettings();
  bindSettings();
  renderLastResult();
})();
