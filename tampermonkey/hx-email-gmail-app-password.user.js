// ==UserScript==
// @name         HX-Email Gmail 应用专用密码助手
// @namespace    https://github.com/hx-email
// @version      0.1.0
// @description  一键完成 Gmail 应用专用密码（App Password）全流程：检测/开启两步验证 → 自动生成 16 位应用密码并复制 → 检查 IMAP 开关，供 HX-Email 使用（默认已登录 Google 账号）
// @author       HX-Email
// @match        https://myaccount.google.com/apppasswords*
// @match        https://myaccount.google.com/signinoptions/two-step-verification*
// @match        https://accounts.google.com/*
// @match        https://mail.google.com/*
// @grant        GM_setClipboard
// @grant        GM_notification
// @grant        GM_getValue
// @grant        GM_setValue
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
  "use strict";

  const APP_PASSWORD_RE = /^([a-z]{4} ?){3}[a-z]{4}$/;
  const EMAIL_RE = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/;
  const AUTO = new URLSearchParams(location.search).get("hx") === "auto" ||
    location.hash.includes("hx=auto");
  const PAGE = detectPage();

  const URLS = {
    appPasswords: "https://myaccount.google.com/apppasswords?hx=auto",
    twoStep: "https://myaccount.google.com/signinoptions/two-step-verification?hx=auto",
    imap: "https://mail.google.com/mail/u/0/#settings/fwdandpop",
    login: "https://accounts.google.com/v3/signin/identifier?continue=https://myaccount.google.com/apppasswords&hl=zh-CN",
  };

  function detectPage() {
    const host = location.hostname;
    const path = location.pathname;
    if (host === "mail.google.com") {
      return location.hash.includes("settings/fwdandpop") ? "imap" : "other";
    }
    if (host === "accounts.google.com") return "login";
    if (host === "myaccount.google.com") {
      if (path.includes("two-step")) return "twostep";
      if (path.includes("apppasswords")) return "apppasswords";
    }
    return "other";
  }

  function makeThrottled(fn, ms = 400) {
    let last = 0;
    return (...args) => {
      const now = Date.now();
      if (now - last < ms) return;
      last = now;
      return fn(...args);
    };
  }

  // ── 设置（油猴存储） ──────────────────────────────────────────────────

  function getAppName() {
    return String(GM_getValue("hx_gmail_app_name", "HX-Email") || "HX-Email");
  }

  function setAppName(name) {
    GM_setValue("hx_gmail_app_name", name || "HX-Email");
  }

  function getBaseUrl() {
    return String(GM_getValue("hx_gmail_base_url", "http://localhost:8000") || "http://localhost:8000");
  }

  // ── 工具 ──────────────────────────────────────────────────────────────

  function allDocuments() {
    const docs = [document];
    for (const frame of document.querySelectorAll("iframe")) {
      try {
        if (frame.contentDocument) docs.push(frame.contentDocument);
      } catch (_err) {
        /* cross-origin */
      }
    }
    return docs;
  }

  function byText(root, matcher) {
    const found = [];
    for (const el of root.querySelectorAll("button, a, [role='button'], input, label, div, span")) {
      if (el.children.length > 0) continue;
      const t = (el.textContent || "").trim();
      if (t && matcher(t)) found.push(el);
    }
    return found;
  }

  function findButton(matcher) {
    for (const doc of allDocuments()) {
      const els = byText(doc, matcher);
      if (els.length) return els[0].closest("button, [role='button'], a") || els[0];
      const aria = [...doc.querySelectorAll("button, [role='button']")].find((el) =>
        matcher(String(el.getAttribute("aria-label") || "")),
      );
      if (aria) return aria;
    }
    return null;
  }

  function setNativeValue(el, value) {
    const proto =
      el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : el instanceof HTMLSelectElement
          ? HTMLSelectElement.prototype
          : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(fn, timeoutMs, intervalMs = 250) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const value = fn();
      if (value) return value;
      if (Date.now() > deadline) return null;
      await sleep(intervalMs);
    }
  }

  function copyText(text) {
    try {
      GM_setClipboard(text);
      return true;
    } catch (_err) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (_err2) {
        ok = false;
      }
      ta.remove();
      return ok;
    }
  }

  function notify(title, body) {
    try {
      GM_notification({ title, text: body, timeout: 5000 });
    } catch (_err) {
      /* 无通知权限时忽略 */
    }
  }

  function openUrl(url) {
    window.open(url, "_blank");
  }

  function extractEmail() {
    for (const doc of allDocuments()) {
      for (const el of doc.querySelectorAll("[aria-label]")) {
        const label = String(el.getAttribute("aria-label") || "");
        const match = label.match(EMAIL_RE);
        if (match && /gmail|googlemail|@/.test(match[0])) return match[0];
      }
      for (const el of doc.querySelectorAll("[data-email]")) {
        const value = String(el.getAttribute("data-email") || "");
        if (EMAIL_RE.test(value)) return value;
      }
    }
    const text = document.body ? document.body.innerText : "";
    const match = text.match(EMAIL_RE);
    return match ? match[0] : "";
  }

  function findPasswordInRoot(root) {
    for (const input of root.querySelectorAll("input")) {
      const value = (input.value || "").trim();
      if (APP_PASSWORD_RE.test(value)) return value;
    }
    for (const el of root.querySelectorAll("div, span, p, td, code")) {
      const t = (el.textContent || "").trim();
      if (APP_PASSWORD_RE.test(t) && t.length <= 19) return t;
    }
    return "";
  }

  function extractGeneratedPassword() {
    for (const doc of allDocuments()) {
      for (const dialog of doc.querySelectorAll("[role='dialog'], [role='alertdialog']")) {
        const pwd = findPasswordInRoot(dialog);
        if (pwd) return pwd;
      }
      const pwd = findPasswordInRoot(doc);
      if (pwd) return pwd;
    }
    return "";
  }

  function bodyHasText(re) {
    const text = document.body ? document.body.innerText : "";
    return re.test(text);
  }

  function isLoginPage() {
    return PAGE === "login" || Boolean(document.querySelector("#identifierId")) ||
      bodyHasText(/登录|Sign in to continue/i);
  }

  function findNameInput() {
    for (const doc of allDocuments()) {
      const inputs = [
        ...doc.querySelectorAll("input[type='text'], input:not([type]), input[type='email'], textarea"),
      ];
      const matched = inputs.find((el) =>
        /自定义|名称|app name|custom|name/i.test(
          `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""}`,
        ),
      );
      if (matched) return matched;
      const visible = inputs.find((el) => el.offsetParent !== null && !el.readOnly && !el.disabled);
      if (visible) return visible;
    }
    return null;
  }

  function findGenerateButton() {
    return findButton((t) => t === "生成" || /^(生成|Generate|Create)$/i.test(t) || /生成|generate|create/i.test(t));
  }

  function fillCustomName(name) {
    for (const doc of allDocuments()) {
      for (const sel of doc.querySelectorAll("select")) {
        const custom = [...sel.options].find((opt) => /自定义|其他|custom|other/i.test(opt.textContent || ""));
        if (custom) {
          setNativeValue(sel, custom.value);
          sel.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    }
    const input = findNameInput();
    if (input) {
      setNativeValue(input, name);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }
    return false;
  }

  // ── 主流程 ────────────────────────────────────────────────────────────

  async function generateAppPassword() {
    const appName = getAppName();
    panel.setStatus(`正在填写应用名称（${appName}）并点击生成…`);
    fillCustomName(appName);
    const generateBtn = findGenerateButton();
    if (!generateBtn) {
      panel.setStatus("未找到「生成」按钮，Google 页面可能已改版。请手动完成一次。");
      return null;
    }
    generateBtn.click();
    await waitFor(
      () => allDocuments().some((doc) => doc.querySelector("[role='dialog'], [role='alertdialog']")),
      8000,
    );
    const password = await waitFor(extractGeneratedPassword, 10000);
    if (!password) {
      panel.setStatus("未能读取到 16 位密码，请在弹出的对话框中手动复制。");
      return null;
    }
    const email = extractEmail();
    const line = email ? `${email}----${password}` : password;
    const copied = copyText(line);
    panel.showResult(password, line, email, copied);
    notify("应用专用密码已生成", copied ? `已复制：${line}` : password);
    return { password, line, email };
  }

  async function handleTwoStepOff() {
    const startBtn = findButton((t) => /开始设置|Get started|开启|Turn on/i.test(t));
    if (startBtn) {
      startBtn.click();
      panel.setStatus(
        "已点击「开始设置」。Google 会要求重新输入密码或手机验证——这部分无法自动完成，" +
          "请在弹出的流程里完成验证；完成后回到「应用专用密码」页继续。",
      );
      return;
    }
    panel.setStatus("未找到「开始设置」按钮，请在该页面手动开启两步验证。");
  }

  function closestLabel(el) {
    const label = el.closest("label");
    if (label) return label.textContent || "";
    const id = el.id;
    if (id) {
      const forLabel = document.querySelector(`label[for='${id}']`);
      if (forLabel) return forLabel.textContent || "";
    }
    const row = el.closest("td, div");
    return row ? (row.textContent || "").slice(0, 80) : "";
  }

  async function fixImap() {
    const enableRadio = await waitFor(
      () =>
        [...allDocuments().flatMap((doc) => [...doc.querySelectorAll("input[type='radio']")])].find(
          (el) => /启用 IMAP|Enable IMAP/i.test(closestLabel(el)),
        ) || null,
      10000,
    );
    if (!enableRadio) {
      panel.setStatus("未找到「启用 IMAP」选项（可能已开启或页面未加载完成）。");
      return false;
    }
    if (enableRadio.checked) {
      panel.setStatus("✓ IMAP 已启用，无需修改。");
      return true;
    }
    enableRadio.click();
    const saveBtn = findButton((t) => /保存更改|Save Changes/i.test(t));
    if (!saveBtn) {
      panel.setStatus("已勾选「启用 IMAP」，但未找到「保存更改」按钮，请手动保存。");
      return false;
    }
    saveBtn.click();
    panel.setStatus("✓ 已勾选「启用 IMAP」并点击保存，稍候生效。");
    return true;
  }

  // ── 浮动面板 ──────────────────────────────────────────────────────────

  const panel = (() => {
    const host = document.createElement("div");
    host.id = "hx-email-gmail-assistant";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
        .panel { position: fixed; right: 16px; bottom: 16px; width: 320px; z-index: 2147483647;
                 background: #fff; color: #202124; border: 1px solid #dadce0; border-radius: 12px;
                 box-shadow: 0 8px 28px rgba(60,64,67,.28); overflow: hidden; font-size: 13px; }
        .head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #1a73e8; color: #fff; }
        .head .title { flex: 1; font-weight: 600; font-size: 13px; }
        .head button { background: none; border: none; color: #fff; cursor: pointer; font-size: 14px; line-height: 1; padding: 2px 6px; border-radius: 4px; }
        .body { padding: 12px; }
        .status { color: #5f6368; line-height: 1.5; margin-bottom: 10px; white-space: pre-line; }
        .row { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn { border: 1px solid #dadce0; background: #f8f9fa; color: #1a73e8; border-radius: 8px; padding: 8px 12px; font-size: 13px; cursor: pointer; font-weight: 500; }
        .btn:hover { background: #e8f0fe; }
        .btn.primary { background: #1a73e8; border-color: #1a73e8; color: #fff; }
        .btn.primary:hover { background: #1765cc; }
        .field { margin-top: 8px; display: flex; gap: 6px; align-items: center; }
        .field input { flex: 1; border: 1px solid #dadce0; border-radius: 6px; padding: 5px 8px; font-size: 12px; min-width: 0; }
        .field label { font-size: 11px; color: #5f6368; white-space: nowrap; }
        .result { margin-top: 10px; border: 1px dashed #1a73e8; border-radius: 8px; padding: 10px; background: #f0f6ff; }
        .result .label { font-size: 11px; color: #5f6368; margin-bottom: 4px; }
        .result .pwd { font-family: Consolas, monospace; font-size: 15px; font-weight: 700; letter-spacing: 1px; color: #174ea6; word-break: break-all; }
        .result .line { font-family: Consolas, monospace; font-size: 11px; color: #3c4043; word-break: break-all; margin-top: 6px; background: #fff; border: 1px solid #dadce0; border-radius: 6px; padding: 6px; }
        .hint { font-size: 11px; color: #80868b; margin-top: 8px; line-height: 1.6; }
        .ok { color: #188038; font-weight: 600; }
        .warn { color: #e37400; font-weight: 600; }
      </style>
      <div class="panel">
        <div class="head">
          <span class="title">HX-Email Gmail 助手</span>
          <button data-act="close" title="关闭">×</button>
        </div>
        <div class="body">
          <div class="status">初始化中…</div>
          <div class="row">
            <button class="btn" data-act="twostep">① 两步验证</button>
            <button class="btn primary" data-act="generate">② 生成应用密码</button>
            <button class="btn" data-act="imap">③ IMAP</button>
          </div>
          <div class="field">
            <label>名称</label>
            <input data-act="app-name" type="text" placeholder="HX-Email" />
          </div>
          <div class="field">
            <label>HX 地址</label>
            <input data-act="base-url" type="text" placeholder="http://localhost:8000" />
          </div>
          <div data-row="result"></div>
          <div class="hint" data-row="hint"></div>
        </div>
      </div>
    `;
    const body = root.querySelector(".body");
    const statusEl = root.querySelector(".status");
    const resultEl = root.querySelector('[data-row="result"]');
    const hintEl = root.querySelector('[data-row="hint"]');
    const appNameInput = root.querySelector('[data-act="app-name"]');
    const baseUrlInput = root.querySelector('[data-act="base-url"]');

    appNameInput.value = getAppName();
    baseUrlInput.value = getBaseUrl();
    appNameInput.addEventListener("change", () => setAppName(appNameInput.value));
    baseUrlInput.addEventListener("change", () => GM_setValue("hx_gmail_base_url", baseUrlInput.value.trim()));

    root.querySelector('[data-act="close"]').addEventListener("click", () => host.remove());
    root.querySelector('[data-act="twostep"]').addEventListener("click", () => openUrl(URLS.twoStep));
    root.querySelector('[data-act="generate"]').addEventListener("click", () => {
      if (PAGE === "apppasswords") void generateAppPassword();
      else openUrl(URLS.appPasswords);
    });
    root.querySelector('[data-act="imap"]').addEventListener("click", () => {
      if (PAGE === "imap") void fixImap();
      else openUrl(URLS.imap);
    });

    document.documentElement.appendChild(host);

    function setStatus(text, kind = "") {
      statusEl.textContent = text;
      statusEl.className = `status ${kind}`;
    }

    function setHint(text) {
      hintEl.textContent = text;
    }

    function showResult(password, line, email, copied) {
      resultEl.innerHTML = `
        <div class="result">
          <div class="label">已生成应用专用密码${copied ? "（已复制到剪贴板）" : ""}</div>
          <div class="pwd">${escapeHtml(password)}</div>
          <div class="line">${escapeHtml(line)}</div>
          <div class="row" style="margin-top:8px">
            <button class="btn" data-act="copy-line">复制导入行</button>
            <button class="btn primary" data-act="open-hx">打开 HX-Email</button>
          </div>
        </div>
      `;
      resultEl.querySelector('[data-act="copy-line"]').addEventListener("click", () => {
        const ok = copyText(line);
        setStatus(ok ? "✓ 导入行已复制" : "复制失败，请手动复制。", "ok");
      });
      resultEl.querySelector('[data-act="open-hx"]').addEventListener("click", () => {
        openUrl(getBaseUrl());
      });
      if (email) {
        setHint(`在 HX-Email「凭证导入」中选择 Gmail → 应用专用密码，粘贴上面的导入行即可。${copied ? "剪贴板已就绪，直接 Ctrl/Cmd+V。" : ""}`);
      }
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      })[ch]);
    }

    return { setStatus, setHint, showResult };
  })();

  // ── 各页面入口 ─────────────────────────────────────────────────────────

  function bootAppPasswords() {
    let autoRan = false;
    panel.setHint("默认使用「HX-Email」作为应用名称（可在面板修改）。生成的密码不会自动过期，除非在 Google 后台撤销。");
    const tick = async () => {
      if (isLoginPage()) {
        panel.setStatus("检测到未登录 Google 账号。请先登录后重新打开此页。", "warn");
        return;
      }
      if (
        bodyHasText(/两步验证未开启|2-?Step Verification is off|Turn on 2-?Step/i) ||
        findButton((t) => /开启两步验证|Turn on 2-?Step/i.test(t))
      ) {
        panel.setStatus("⚠ 两步验证未开启，无法生成应用专用密码。点击「① 两步验证」去开启（需完成 Google 的密码/手机验证）。", "warn");
        if (AUTO && !autoRan) {
          autoRan = true;
          await sleep(600);
          location.href = URLS.twoStep;
        }
        return;
      }
      if (extractGeneratedPassword()) {
        const password = extractGeneratedPassword();
        const email = extractEmail();
        const line = email ? `${email}----${password}` : password;
        const copied = copyText(line);
        panel.setStatus(copied ? "检测到页面上的应用专用密码，已复制到剪贴板：" : "检测到页面上的应用专用密码：", "ok");
        panel.showResult(password, line, email, copied);
        return;
      }
      if (findGenerateButton() || findNameInput()) {
        panel.setStatus("表单已就绪，点击「② 生成应用密码」即可自动生成并复制 16 位密码。");
        if (AUTO && !autoRan) {
          autoRan = true;
          panel.setStatus("自动模式：正在生成应用专用密码…");
          await generateAppPassword();
        }
        return;
      }
      panel.setStatus("页面加载中，等待表单就绪…");
    };
    tick();
    const tickT = makeThrottled(tick);
    const observer = new MutationObserver(() => void tickT());
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 60000);
  }

  function bootTwoStep() {
    let autoRan = false;
    panel.setHint("两步验证开启后才能生成应用专用密码。");
    const tick = () => {
      if (isLoginPage()) {
        panel.setStatus("检测到未登录。请先登录 Google 账号。", "warn");
        return;
      }
      if (
        bodyHasText(/已开启|开启.?状态|Turned on/i) &&
        !findButton((t) => /开始设置|Get started/i.test(t))
      ) {
        panel.setStatus("✓ 两步验证已开启。去生成应用专用密码吧。", "ok");
        return;
      }
      if (findButton((t) => /开始设置|Get started|Turn on 2-?Step/i.test(t))) {
        panel.setStatus("两步验证尚未开启。点击「开始设置」后请完成 Google 的密码/手机验证（无法自动完成）。", "warn");
        if (AUTO && !autoRan) {
          autoRan = true;
          void handleTwoStepOff();
        }
        return;
      }
      panel.setStatus("页面加载中…");
    };
    tick();
    const tickT = makeThrottled(tick);
    const observer = new MutationObserver(() => void tickT());
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 60000);
  }

  function bootImap() {
    panel.setHint("个人 Gmail 通常默认启用 IMAP；此步骤仅在关闭时自动打开并保存。");
    const tick = () => {
      const radio = [...allDocuments().flatMap((doc) => [...doc.querySelectorAll("input[type='radio']")])].find(
        (el) => /启用 IMAP|Enable IMAP/i.test(closestLabel(el)),
      );
      if (radio) {
        if (radio.checked) panel.setStatus("✓ IMAP 已启用，无需修改。", "ok");
        else panel.setStatus("IMAP 当前为关闭状态，点击「③ IMAP」一键开启并保存。", "warn");
        return;
      }
      panel.setStatus("正在加载 Gmail 设置…（若长时间无响应，请确认已进入「设置 → 转发和 POP/IMAP」）");
    };
    tick();
    const tickT = makeThrottled(tick);
    const observer = new MutationObserver(() => void tickT());
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 90000);
    if (AUTO) sleep(2500).then(() => void fixImap());
  }

  function bootLogin() {
    panel.setStatus("请在 Google 登录页完成登录。登录后会自动回到应用专用密码页。", "warn");
  }

  function bootOther() {
    panel.setStatus("此页面暂不支持。请打开应用专用密码页或 Gmail 设置页使用。");
  }

  if (document.documentElement) {
    if (PAGE === "apppasswords") bootAppPasswords();
    else if (PAGE === "twostep") bootTwoStep();
    else if (PAGE === "imap") bootImap();
    else if (PAGE === "login") bootLogin();
    else bootOther();
  }
})();
