#!/usr/bin/env node
/**
 * Compatibility check: baked-in Azure app values vs HX-Email source defaults.
 * Read-only. Does not modify non-tampermonkey files.
 *
 * Usage: node tampermonkey/compat-check.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

const EXPECTED_SCOPE =
  "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send";
const EXPECTED_REDIRECT = "http://localhost:8000/token-tool/callback";
const EXPECTED_TENANT = "consumers";

function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function fail(msg) {
  console.error("FAIL:", msg);
  process.exitCode = 1;
}

function ok(msg) {
  console.log("OK  :", msg);
}

function main() {
  const app = JSON.parse(read("tampermonkey/azure-app.json"));
  const cfg = app.hx_email_token_tool;
  const userscript = read("tampermonkey/hx-email-azure-app-cli.user.js");
  const serverConfig = read("server/src/hx_email/config.py");
  const tokenRoutes = read(
    "server/src/hx_email/api/impl/mail/token_tool_routes.py",
  );
  const tokenTool = read("web/src/pages/TokenTool.tsx");
  const sendMail = read("server/src/hx_email/server/mail/send_mail.py");
  const credentials = read(
    "server/src/hx_email/server/mail/impl/sending/credentials.py",
  );

  // azure-app.json contract
  if (cfg.scope !== EXPECTED_SCOPE) fail("azure-app.json scope mismatch");
  else ok("azure-app.json scope matches HX-Email Graph contract");

  if (cfg.redirect_uri !== EXPECTED_REDIRECT)
    fail("azure-app.json redirect_uri mismatch");
  else ok("azure-app.json redirect_uri matches Token Tool default");

  if (cfg.tenant !== EXPECTED_TENANT) fail("azure-app.json tenant mismatch");
  else ok("azure-app.json tenant=consumers");

  if (cfg.client_secret !== null) fail("client_secret must be null");
  else ok("public client (no client_secret)");

  if (!app.public_client || !app.allow_public_client_flows)
    fail("public client flags missing");
  else ok("public client flags set");

  if (!cfg.client_id || cfg.client_id.length < 30)
    fail("client_id looks invalid");
  else ok("client_id present: " + cfg.client_id);

  // userscript embeds same client id + scope + redirect
  for (const needle of [
    cfg.client_id,
    EXPECTED_SCOPE,
    EXPECTED_REDIRECT,
    "Mail.Send",
    "Mail.Read",
  ]) {
    if (!userscript.includes(needle))
      fail("userscript missing: " + needle.slice(0, 60));
    else ok("userscript contains " + needle.slice(0, 48));
  }

  // server MICROSOFT_MAIL_SCOPE
  if (!serverConfig.includes("Mail.Read") || !serverConfig.includes("Mail.Send"))
    fail("server config missing Mail.Read/Mail.Send");
  else ok("server MICROSOFT_MAIL_SCOPE includes Mail.Read + Mail.Send");

  if (!serverConfig.includes("offline_access"))
    fail("server scope missing offline_access");
  else ok("server scope includes offline_access");

  // token tool default redirect
  if (!tokenRoutes.includes(EXPECTED_REDIRECT))
    fail("token_tool_routes default redirect mismatch");
  else ok("token_tool_routes DEFAULT_REDIRECT_URI matches");

  // web Token Tool graph preset
  if (
    !tokenTool.includes("https://graph.microsoft.com/Mail.Read") ||
    !tokenTool.includes("https://graph.microsoft.com/Mail.Send")
  )
    fail("web TokenTool graph preset missing Mail.Read/Send");
  else ok("web TokenTool Graph preset matches");

  if (!tokenTool.includes('tenant: "consumers"'))
    fail("web TokenTool tenant not consumers");
  else ok("web TokenTool tenant=consumers");

  // send mail graph strategy
  if (!credentials.includes("outlook_graph_send_mail"))
    fail("send credentials missing outlook_graph_send_mail");
  else ok("send path uses outlook_graph_send_mail");

  if (!sendMail.includes("Mail.Send"))
    fail("send_mail guidance missing Mail.Send");
  else ok("send_mail documents Mail.Send requirement");

  // permission completeness for read+send
  const perms = app.delegated_permissions.microsoft_graph;
  for (const p of ["offline_access", "Mail.Read", "Mail.Send", "User.Read"]) {
    if (!perms.includes(p)) fail("missing delegated permission: " + p);
    else ok("delegated permission: " + p);
  }

  if (process.exitCode) {
    console.error("\ncompat-check FAILED");
    process.exit(process.exitCode);
  }
  console.log("\ncompat-check PASSED — Azure app is compatible with HX-Email Graph read/send");
}

main();
