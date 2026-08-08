// Google OAuth brand verification needs publicly reachable static pages at
// clean URLs. nginx.conf.template redirects these paths to the .html files in
// production; this plugin keeps dev and preview behavior identical.
var BRAND_REDIRECTS = {
    "/home": "/home.html",
    "/home/": "/home.html",
    "/privacy": "/privacy.html",
    "/privacy/": "/privacy.html",
    "/privacy-policy": "/privacy.html",
};
var redirectBrandPaths = function (req, res, next) {
    var _a, _b;
    var path = (_b = (_a = req.url) === null || _a === void 0 ? void 0 : _a.split("?")[0]) !== null && _b !== void 0 ? _b : "";
    var target = BRAND_REDIRECTS[path];
    if (target) {
        res.statusCode = 302;
        res.setHeader("Location", target);
        res.end();
        return;
    }
    next();
};
export var brandRedirectPlugin = function () { return ({
    name: "brand-pages-redirect",
    configureServer: function (server) {
        server.middlewares.use(redirectBrandPaths);
    },
    configurePreviewServer: function (server) {
        server.middlewares.use(redirectBrandPaths);
    },
}); };
