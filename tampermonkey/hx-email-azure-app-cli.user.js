// ==UserScript==
// @name         HX-Email Azure 应用注册助手
// @namespace    https://github.com/hx-email
// @version      1.1.1
// @description  一键辅助 Microsoft Entra / Azure 应用注册，供 HX-Email Token Tool 使用（公共客户端，Graph Mail.Read + Mail.Send）
// @author       HX-Email
// @match        https://portal.azure.com/*
// @match        https://entra.microsoft.com/*
// @match        https://*.portal.azure.com/*
// @match        http://localhost/*
// @match        http://127.0.0.1/*
// @grant        GM_setClipboard
// @grant        GM_notification
// @grant        GM_getValue
// @grant        GM_setValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  /** HX-Email Token Tool 默认值（须与服务端 MICROSOFT_MAIL_SCOPE 一致）。 */
  const HX = {
    appName: "HX-Email",
    clientId: "75b83d3c-e645-464d-beac-c7e7c322f9b0",
    objectId: "e5bd6035-bd08-4436-9a01-6dc9a8c991e6",
    tenantId: "03d895d4-b066-4a54-8433-56395b17b8ef",
    tenant: "consumers",
    redirectUri: "http://localhost:8000/token-tool/callback",
    scope:
      "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send",
    mode: "graph",
    promptConsent: true,
    signInAudience: "AzureADandPersonalMicrosoftAccount",
    platform: "Mobile and desktop applications / Public client",
    delegatedPermissions: [
      "offline_access",
      "Mail.Read",
      "Mail.Send",
      "User.Read",
    ],
  };

  const STORAGE_KEY = "hx_email_azure_app_override";

  function loadConfig() {
    try {
      const raw = GM_getValue(STORAGE_KEY, "");
      if (!raw) return { ...HX };
      const parsed = JSON.parse(String(raw));
      return { ...HX, ...parsed };
    } catch {
      return { ...HX };
    }
  }

  function saveConfig(partial) {
    const next = { ...loadConfig(), ...partial };
    GM_setValue(STORAGE_KEY, JSON.stringify(next));
    return next;
  }

  function copyText(text, label) {
    const value = String(text || "");
    if (!value) {
      notify(label + " 为空", true);
      return;
    }
    try {
      if (typeof GM_setClipboard === "function") {
        GM_setClipboard(value);
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        void navigator.clipboard.writeText(value);
      } else {
        const ta = document.createElement("textarea");
        ta.value = value;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      notify(label + " 已复制");
    } catch (err) {
      notify("复制失败: " + String(err), true);
    }
  }

  function notify(message, isError) {
    try {
      if (typeof GM_notification === "function") {
        GM_notification({
          title: "HX-Email Azure 应用助手",
          text: message,
          timeout: 2500,
        });
      }
    } catch {
      /* ignore */
    }
    setStatus(message, isError);
  }

  function setStatus(message, isError) {
    const el = document.getElementById("hx-email-azure-status");
    if (!el) return;
    el.textContent = message;
    el.style.color = isError ? "#f85149" : "#3fb950";
  }

  function isAzureHost() {
    const h = location.hostname;
    return (
      h === "portal.azure.com" ||
      h.endsWith(".portal.azure.com") ||
      h === "entra.microsoft.com"
    );
  }

  function isHxTokenToolHost() {
    const h = location.hostname;
    return h === "localhost" || h === "127.0.0.1";
  }

  function openAppOverview(cfg) {
    const url =
      "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Overview/appId/" +
      encodeURIComponent(cfg.clientId) +
      "/objectId/" +
      encodeURIComponent(cfg.objectId) +
      "/isMSAApp~/false/defaultBlade/Overview/appSignInAudience/AzureADandPersonalMicrosoftAccount";
    location.href = url;
  }

  function openApiPermissions(cfg) {
    const url =
      "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/CallAnAPI/appId/" +
      encodeURIComponent(cfg.clientId) +
      "/objectId/" +
      encodeURIComponent(cfg.objectId);
    location.href = url;
  }

  function openAuthentication(cfg) {
    const url =
      "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Authentication/appId/" +
      encodeURIComponent(cfg.clientId) +
      "/objectId/" +
      encodeURIComponent(cfg.objectId);
    location.href = url;
  }

  function openNewRegistration() {
    location.href =
      "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false";
  }

  function openAppList() {
    location.href =
      "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade/quickStartType~/null/sourceType/Microsoft_AAD_IAM";
  }

  function buildTokenToolJson(cfg) {
    return JSON.stringify(
      {
        client_id: cfg.clientId,
        redirect_uri: cfg.redirectUri,
        scope: cfg.scope,
        tenant: cfg.tenant,
        prompt_consent: cfg.promptConsent,
        mode: cfg.mode,
      },
      null,
      2,
    );
  }

  function buildKeysBlock(cfg) {
    return [
      "=== HX-Email Microsoft OAuth（复制到 Token Tool）===",
      "Client ID:     " + cfg.clientId,
      "Object ID:     " + cfg.objectId,
      "Tenant ID:     " + cfg.tenantId,
      "Tenant:        " + cfg.tenant,
      "Redirect URI:  " + cfg.redirectUri,
      "Scope:         " + cfg.scope,
      "Mode:          " + cfg.mode,
      "Public Client: 是（allowPublicClient / isFallbackPublicClient = true）",
      "Audience:      " + cfg.signInAudience,
      "Platform:      " + cfg.platform,
      "Permissions:   " + cfg.delegatedPermissions.join(", "),
      "说明:          无 client_secret（公共客户端 + PKCE）",
    ].join("\n");
  }

  function tryFillHxTokenTool(cfg) {
    const clientInputs = [
      ...document.querySelectorAll("input, textarea"),
    ].filter((el) => {
      const name = (
        (el.getAttribute("name") || "") +
        " " +
        (el.getAttribute("id") || "") +
        " " +
        (el.getAttribute("placeholder") || "") +
        " " +
        (el.getAttribute("aria-label") || "")
      ).toLowerCase();
      return /client.?id|redirect|scope|tenant/.test(name);
    });

    let filled = 0;
    for (const el of clientInputs) {
      const key = (
        (el.getAttribute("name") || "") +
        " " +
        (el.getAttribute("id") || "") +
        " " +
        (el.getAttribute("placeholder") || "") +
        " " +
        (el.getAttribute("aria-label") || "")
      ).toLowerCase();
      let value = "";
      if (key.includes("client")) value = cfg.clientId;
      else if (key.includes("redirect")) value = cfg.redirectUri;
      else if (key.includes("scope")) value = cfg.scope;
      else if (key.includes("tenant")) value = cfg.tenant;
      if (!value) continue;
      el.focus();
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      filled += 1;
    }
    return filled;
  }

  function styleButton(btn, primary) {
    btn.style.cssText = [
      "display:inline-flex",
      "align-items:center",
      "justify-content:center",
      "gap:4px",
      "padding:6px 10px",
      "border-radius:6px",
      "border:1px solid " + (primary ? "#1f6feb" : "#30363d"),
      "background:" + (primary ? "#1f6feb" : "#21262d"),
      "color:#e6edf3",
      "font:12px/1.3 ui-sans-serif,system-ui,sans-serif",
      "cursor:pointer",
      "white-space:nowrap",
    ].join(";");
  }

  function makeButton(label, onClick, primary) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    styleButton(btn, primary);
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      onClick();
    });
    return btn;
  }

  function makePanel() {
    if (document.getElementById("hx-email-azure-panel")) return;

    const cfg = loadConfig();
    const root = document.createElement("div");
    root.id = "hx-email-azure-panel";
    root.style.cssText = [
      "position:fixed",
      "z-index:2147483646",
      "right:16px",
      "bottom:16px",
      "width:360px",
      "max-height:80vh",
      "overflow:auto",
      "background:#0d1117",
      "color:#e6edf3",
      "border:1px solid #30363d",
      "border-radius:12px",
      "box-shadow:0 12px 40px rgba(0,0,0,.45)",
      "font:12px/1.45 ui-sans-serif,system-ui,sans-serif",
      "padding:12px",
    ].join(";");

    const title = document.createElement("div");
    title.style.cssText =
      "display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;";
    title.innerHTML =
      '<strong style="font-size:13px">HX-Email Azure 应用助手</strong>';

    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "×";
    close.style.cssText =
      "border:0;background:transparent;color:#8b949e;cursor:pointer;font-size:14px;";
    close.addEventListener("click", () => root.remove());
    title.appendChild(close);

    const meta = document.createElement("div");
    meta.style.cssText = "color:#8b949e;margin-bottom:8px;word-break:break-all;";
    meta.innerHTML =
      "应用: <b style='color:#e6edf3'>" +
      cfg.appName +
      "</b><br>Client ID: <code style='color:#79c0ff'>" +
      cfg.clientId +
      "</code>";

    const keys = document.createElement("textarea");
    keys.readOnly = true;
    keys.value = buildKeysBlock(cfg);
    keys.style.cssText = [
      "width:100%",
      "height:150px",
      "resize:vertical",
      "box-sizing:border-box",
      "background:#161b22",
      "color:#c9d1d9",
      "border:1px solid #30363d",
      "border-radius:8px",
      "padding:8px",
      "font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace",
      "margin-bottom:8px",
    ].join(";");

    const row1 = document.createElement("div");
    row1.style.cssText =
      "display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;";
    row1.appendChild(
      makeButton("复制 Client ID", () => copyText(cfg.clientId, "Client ID"), true),
    );
    row1.appendChild(
      makeButton("复制 Redirect URI", () =>
        copyText(cfg.redirectUri, "Redirect URI"),
      ),
    );
    row1.appendChild(
      makeButton("复制 Scope", () => copyText(cfg.scope, "Scope")),
    );
    row1.appendChild(
      makeButton("复制全部密钥", () => copyText(keys.value, "全部密钥")),
    );
    row1.appendChild(
      makeButton("复制 Token JSON", () =>
        copyText(buildTokenToolJson(cfg), "Token Tool JSON"),
      ),
    );

    const row2 = document.createElement("div");
    row2.style.cssText =
      "display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;";
    if (isAzureHost()) {
      row2.appendChild(
        makeButton("应用概览", () => openAppOverview(cfg), true),
      );
      row2.appendChild(
        makeButton("身份验证", () => openAuthentication(cfg)),
      );
      row2.appendChild(
        makeButton("API 权限", () => openApiPermissions(cfg)),
      );
      row2.appendChild(makeButton("应用列表", () => openAppList()));
      row2.appendChild(makeButton("新建注册", () => openNewRegistration()));
    }
    if (isHxTokenToolHost()) {
      row2.appendChild(
        makeButton(
          "填充 Token Tool 字段",
          () => {
            const n = tryFillHxTokenTool(cfg);
            notify(
              n > 0
                ? "已填充 " + n + " 个字段，请在 Token Tool 中保存配置。"
                : "当前页面未找到匹配字段",
              n === 0,
            );
          },
          true,
        ),
      );
    }

    const checklist = document.createElement("div");
    checklist.style.cssText =
      "margin-top:4px;padding:8px;border:1px solid #30363d;border-radius:8px;background:#161b22;color:#8b949e;";
    checklist.innerHTML = [
      "<div style='color:#e6edf3;font-weight:600;margin-bottom:4px'>Azure 检查清单（HX-Email）</div>",
      "<ol style='margin:0;padding-left:18px'>",
      "<li>受众 = 任何组织目录 + 个人 Microsoft 帐户</li>",
      "<li>平台 = 移动和桌面应用程序（公共客户端）</li>",
      "<li>重定向 URI = " + cfg.redirectUri + "</li>",
      "<li>允许公共客户端流 = 是</li>",
      "<li>委托权限: offline_access, Mail.Read, Mail.Send, User.Read</li>",
      "<li>无 client_secret；Token Tool 使用 PKCE + tenant=consumers</li>",
      "</ol>",
    ].join("");

    const status = document.createElement("div");
    status.id = "hx-email-azure-status";
    status.style.cssText = "margin-top:8px;min-height:16px;color:#8b949e;";
    status.textContent = isAzureHost()
      ? "已检测到 Azure 页面，可用复制 / 跳转按钮。"
      : isHxTokenToolHost()
        ? "已检测到本机页面，可复制密钥或尝试自动填充。"
        : "就绪。";

    const override = document.createElement("details");
    override.style.marginTop = "8px";
    override.innerHTML =
      "<summary style='cursor:pointer;color:#8b949e'>覆盖 Client ID / Redirect（高级）</summary>";
    const form = document.createElement("div");
    form.style.cssText = "display:grid;gap:6px;margin-top:6px;";
    const clientInput = document.createElement("input");
    clientInput.placeholder = "Client ID";
    clientInput.value = cfg.clientId;
    clientInput.style.cssText =
      "width:100%;box-sizing:border-box;padding:6px 8px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;";
    const redirectInput = document.createElement("input");
    redirectInput.placeholder = "Redirect URI";
    redirectInput.value = cfg.redirectUri;
    redirectInput.style.cssText = clientInput.style.cssText;
    const saveBtn = makeButton("保存覆盖", () => {
      const next = saveConfig({
        clientId: clientInput.value.trim() || HX.clientId,
        redirectUri: redirectInput.value.trim() || HX.redirectUri,
      });
      keys.value = buildKeysBlock(next);
      meta.innerHTML =
        "应用: <b style='color:#e6edf3'>" +
        next.appName +
        "</b><br>Client ID: <code style='color:#79c0ff'>" +
        next.clientId +
        "</code>";
      notify("覆盖已保存");
    });
    const resetBtn = makeButton("重置为内置应用", () => {
      GM_setValue(STORAGE_KEY, "");
      const next = loadConfig();
      clientInput.value = next.clientId;
      redirectInput.value = next.redirectUri;
      keys.value = buildKeysBlock(next);
      meta.innerHTML =
        "应用: <b style='color:#e6edf3'>" +
        next.appName +
        "</b><br>Client ID: <code style='color:#79c0ff'>" +
        next.clientId +
        "</code>";
      notify("已重置为默认 HX-Email 应用");
    });
    form.appendChild(clientInput);
    form.appendChild(redirectInput);
    form.appendChild(saveBtn);
    form.appendChild(resetBtn);
    override.appendChild(form);

    root.appendChild(title);
    root.appendChild(meta);
    root.appendChild(keys);
    root.appendChild(row1);
    root.appendChild(row2);
    root.appendChild(checklist);
    root.appendChild(override);
    root.appendChild(status);
    document.documentElement.appendChild(root);
  }

  function boot() {
    makePanel();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
