import type { Plugin } from "vite";

// Google OAuth brand verification needs publicly reachable static pages at
// clean URLs. nginx.conf.template redirects these paths to the .html files in
// production; this plugin keeps dev and preview behavior identical.
const BRAND_REDIRECTS: Record<string, string> = {
  "/": "/home.html",
  "/home": "/home.html",
  "/home/": "/home.html",
  "/privacy": "/privacy.html",
  "/privacy/": "/privacy.html",
  "/privacy-policy": "/privacy.html",
};

const redirectBrandPaths = (
  req: { url?: string },
  res: { statusCode: number; setHeader: (name: string, value: string) => void; end: () => void },
  next: () => void,
): void => {
  const path = req.url?.split("?")[0] ?? "";
  const target = BRAND_REDIRECTS[path];
  if (target) {
    res.statusCode = 302;
    res.setHeader("Location", target);
    res.end();
    return;
  }
  next();
};

export const brandRedirectPlugin = (): Plugin => ({
  name: "brand-pages-redirect",
  configureServer(server) {
    server.middlewares.use(redirectBrandPaths);
  },
  configurePreviewServer(server) {
    server.middlewares.use(redirectBrandPaths);
  },
});
