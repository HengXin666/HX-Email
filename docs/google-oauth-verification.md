# Google OAuth 应用品牌验证

本文档说明 HX-Email 面向 Google OAuth 品牌验证（`support.google.com/cloud/answer/13807376`）时,哪些内容由代码保证,哪些需要在 Google Cloud 控制台手动配置。

## 公开页面(代码侧,已就绪)

| 用途 | URL | 来源 |
| --- | --- | --- |
| 应用首页(公开,无需登录) | `/home.html`,站点根路径 `/` 会 301 到该页 | `web/public/home.html` |
| 隐私政策 | `/privacy.html` | `web/public/privacy.html` |

- 生产环境由 `web/nginx.conf.template` 将 `/`、`/home`、`/privacy` 等路径 301 到对应的静态页;开发与预览环境由 `web/brand_redirect_plugin.ts` 保持一致。
- 首页明确描述了应用用途(多邮箱统一管理、验证码自动读取、平台绑定等),并链接回登录页 `/login`,Google 审核员无需登录即可看到。

## 控制台侧配置(部署方手工操作)

1. **域名所有权验证**(解决"首页网址对应的网站未注册到名下"):
   - 在 [Google Search Console](https://search.google.com/search-console) 添加资源,选择域名方式并添加 DNS TXT 记录,或按 `https://email.woa.qzz.io/` 添加"网址前缀"资源并完成验证。
   - 在 Google Cloud Console 的 OAuth 同意屏幕 -> "授权网域" 中加入 `email.woa.qzz.io`(必须是已验证域名)。
2. **应用名称统一为 `HX-Email`**(解决"应用名称与首页不一致"):
   - OAuth 同意屏幕的"应用名称"当前配置为 `HX-EMail`,需改为与首页一致的 `HX-Email`。
3. **填写公开链接**:
   - 应用首页: `https://email.woa.qzz.io/home.html`
   - 应用隐私政策: `https://email.woa.qzz.io/privacy.html`
4. 确认应用处于"正在验证"状态并重新提交验证,等待 Google 审核。

## 本地验证命令

```bash
cd web
npm install
npm test                 # 静态页与重定向行为测试
npm run build && npm run preview   # 本地预览:/ 与 /home 应 301 到 /home.html
```
