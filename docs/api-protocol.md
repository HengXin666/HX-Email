# API 协议约定

本项目 API 遵循业界最通用的组合: **REST 风格 + JSON + OpenAPI 3.1 自描述**。
没有自造协议 — 任何标准 HTTP 客户端、Swagger 工具、openapi-generator 生成的
SDK 都能直接对接。

## 自描述 (唯一权威来源)

服务自动暴露机器可读的接口契约, 文档与代码永不脱节:

| 路径            | 内容                                                           |
| --------------- | -------------------------------------------------------------- |
| `/openapi.json` | OpenAPI 3.1 规范 (可喂给 openapi-generator / Postman / Apifox) |
| `/docs`         | Swagger UI 交互式文档 (带 Authorize 按钮, 可直接调试)          |
| `/redoc`        | ReDoc 阅读版文档                                               |

## 两个 API 面

| 面       | 前缀              | 认证                                       | 用途                         |
| -------- | ----------------- | ------------------------------------------ | ---------------------------- |
| 业务 API | `/api/v1/*`       | `Authorization: Bearer <token>` (RFC 6750) | Web 前端与个人脚本           |
| 外部 API | `/api/external/*` | `Authorization: Bearer <api-key>`          | 自动化程序对接 (取码/邮箱池) |

- Bearer token 由 `POST /api/v1/auth/login` 获取。
- API Key 在系统设置中生成, 以 `Authorization: Bearer <api-key>` 携带; 外部 API 带内置限流 (超限返回 429)。
- 认证失败返回 401 并携带 `WWW-Authenticate` 头 (RFC 6750/9110)。

## 请求 / 响应约定

- 请求体与响应体一律 JSON (`Content-Type: application/json`)。
- URL: 资源用复数名词 + kebab-case (`/usable-emails/{id}`);
  无法建模为资源的操作用动词子路径 (`/activate`, `/refresh`, `/claim`),
  与 GitHub/Stripe 的 pragmatic REST 一致。
- 方法语义遵循 RFC 9110: GET 无副作用, 创建 POST → 201, 删除 → 204 或
  `{"success": true}`, 触发类操作一律 POST。
- 分页: `?limit=&offset=`, 响应含 `total`。
- 错误统一为 FastAPI 约定的 `{"detail": "<message>"}`;
  请求体校验失败返回 422 (detail 为字段级错误数组)。
- 长任务进度 (批量刷新) 用 SSE (`text/event-stream`), POST 发起,
  事件为 JSON: `{"type": "start|progress|complete", ...}`。
- 版本策略: 破坏性变更才升 `/api/v2`; 新增字段/端点不算破坏。

## 废弃别名 (仍可用, 勿新接)

历史路径保留兼容, 但在 OpenAPI 中标记 `deprecated: true` (Swagger UI 显示删除线),
新对接一律使用规范路径:

| 废弃别名                                          | 规范路径                                  |
| ------------------------------------------------- | ----------------------------------------- |
| `GET /api/v1/email/{addr}/{id}`                   | `GET /api/v1/emails/{addr}/{id}`          |
| `GET /api/v1/overview/verification`               | `GET /api/v1/overview/verification-stats` |
| `GET /api/v1/overview/external-api`               | `GET /api/v1/overview/external-api-stats` |
| `GET /api/v1/overview/pool`                       | `GET /api/v1/overview/pool-stats`         |
| `GET /api/v1/email-accounts/refresh-all` 等触发类 | 同路径 `POST`                             |

## 快速上手

```bash
# 登录拿 token
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# 业务 API
curl -s http://127.0.0.1:8080/api/v1/usable-emails \
  -H "Authorization: Bearer $TOKEN"

# 外部 API (自动化取码)
curl -s "http://127.0.0.1:8080/api/external/verification-code?email=xx@example.com" \
  -H "Authorization: Bearer $API_KEY"
```

## 生成客户端 SDK

```bash
npx @openapitools/openapi-generator-cli generate \
  -i http://127.0.0.1:8080/openapi.json -g python -o ./hx-email-sdk
```
