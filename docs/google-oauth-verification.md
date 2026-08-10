# Google OAuth 应用品牌验证

本文档说明 HX-Email 面向 Google OAuth 品牌验证（`support.google.com/cloud/answer/13807376`）时,哪些内容由代码保证,哪些需要在 Google Cloud 控制台手动配置。

## 公开页面(代码侧,已就绪)

| 用途                    | URL                                                               | 来源                        |
| ----------------------- | ----------------------------------------------------------------- | --------------------------- |
| 应用首页(公开,无需登录) | `/home`;站点根路径 `/`、`/home.html` 均直接输出应用外壳(无重定向) | `web/src/pages/Home.tsx`    |
| 隐私政策                | `/privacy`、`/privacy-policy`、`/privacy.html`                    | `web/src/pages/Privacy.tsx` |
| 服务条款                | `/terms`、`/terms-of-service`、`/terms.html`                      | `web/src/pages/Terms.tsx`   |

- 三个公开页面已整体迁移到 React 体系(不再使用静态 HTML),由 react-router 渲染;品牌信息与结构化数据(SoftwareApplication)固化在 `web/index.html`,随应用外壳一并下发。
- 生产环境由 `web/nginx.conf.template` 将 `/`、`/home`、`/privacy` 等路径直接输出 SPA 外壳(不产生重定向,避免代理改写 Location 导致端口/协议异常);开发与预览环境由 Vite 的 SPA 回退保持一致。
- 首页明确描述了应用用途(多邮箱统一管理、验证码自动读取、平台绑定等),并链接回登录页 `/login`,Google 审核员无需登录即可看到。
- 中文渲染依赖内置的 Noto Sans SC 简体字体(`web/src/assets/fonts/`),任何环境(含无中文字体的无头浏览器)都不会出现“口口口”乱码。
- 验证文件 `google<hash>.html` 由后台「系统设置 → 基础 → Google 站点验证」上传,由后端在站点根路径公开提供。

## 部署自检(重新提交验证前必须全部通过)

```bash
# 首页与隐私政策必须可公开访问(200,text/html)
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://email.woa.qzz.io/home
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://email.woa.qzz.io/privacy
# 站点根路径必须直接返回应用外壳,不能 301 到 http://...:端口 之类的内部地址
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://email.woa.qzz.io/
# 上传验证文件后,该地址必须返回文件原文
curl -s https://email.woa.qzz.io/google18261d952ce2f02c.html
```

常见问题:若根路径 301 到 `http://域名:端口/...`(内部端口泄漏)或目标不可达,说明入口代理/nginx 配置没有使用仓库中的 `web/nginx.conf.template`(该模板为直接输出、无重定向),请重新按模板部署前端。

## 控制台侧配置(部署方手工操作)

1. **域名所有权验证**(解决"首页网址对应的网站未注册到名下"):
   - 在 [Google Search Console](https://search.google.com/search-console) 添加资源,推荐"网址前缀"方式并按 `https://email.woa.qzz.io/` 添加,验证方式选择"HTML 文件"。
   - 下载 Google 生成的 `google<hash>.html` 文件,在 HX-Email 管理后台「系统设置 → 基础 → Google 站点验证」中上传;系统会把它公开提供在 `https://email.woa.qzz.io/google<hash>.html`,点击 Search Console 的"验证"即可完成。
   - 若希望用域名方式验证,也可添加 DNS TXT 记录。
   - 上传后在 Search Console 点击"验证",状态变为"已验证"后,在 Google Cloud Console 的 OAuth 同意屏幕 -> "授权网域" 中加入 `email.woa.qzz.io`(必须是已验证域名)。
2. **应用名称统一为 `HX-Email`**(解决"应用名称与首页不一致"):
   - OAuth 同意屏幕的"应用名称"必须与首页品牌完全一致,统一为 `HX-Email`(注意大小写,勿写 `HX-EMail`)。
3. **填写公开链接**:
   - 应用首页: `https://email.woa.qzz.io/home`(不要填根域名,避免经重定向)
   - 应用隐私政策: `https://email.woa.qzz.io/privacy`
   - 应用服务条款: `https://email.woa.qzz.io/terms`
4. 确认应用处于"正在验证"状态并重新提交验证,等待 Google 审核。

> Google 要求同意屏幕上的三个链接(应用首页、隐私权政策、服务条款)都指向公开可访问的页面,三者缺一不可。
> 注意:品牌页面由 React 客户端渲染,审核浏览器会执行 JS;如审核环境完全不执行 JS,页面正文不会出现在初始 HTML 中。仓库测试(`web/src/static-pages.test.tsx`)会持续校验三个页面的必填内容与品牌一致性。

## 本地验证命令

```bash
cd web
npm install
npm test                 # React 品牌页面与 SPA 回退行为测试
npm run build && npm run preview   # 本地预览:/ 与 /home 输出应用外壳并渲染首页内容
```
