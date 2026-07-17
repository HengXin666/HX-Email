# Python 后端库

## 默认库

| 用途          | 默认选择 | 备注                        | 官方来源                        |
| ------------- | -------- | --------------------------- | ------------------------------- |
| Web 框架      | FastAPI  | 默认推荐；适合现代 API 后端 | <https://fastapi.tiangolo.com/> |
| ASGI 运行     | Uvicorn  | FastAPI 常用 ASGI server    | <https://www.uvicorn.org/>      |
| 数据模型/校验 | Pydantic | FastAPI 默认生态            | <https://pydantic.dev/>         |

## 实时通信库

| 用途         | 默认选择                      | 备注                                       | 官方来源                                                    |
| ------------ | ----------------------------- | ------------------------------------------ | ----------------------------------------------------------- |
| SSE          | FastAPI `EventSourceResponse` | FastAPI 0.135.0+ 优先使用                  | <https://fastapi.tiangolo.com/tutorial/server-sent-events/> |
| SSE 兼容方案 | sse-starlette                 | 旧 FastAPI 或需要 Starlette SSE 支持时使用 | <https://github.com/sysid/sse-starlette>                    |
| WebSocket    | FastAPI `WebSocket`           | 双向实时通信默认使用                       | <https://fastapi.tiangolo.com/advanced/websockets/>         |

## 可选库

| 用途        | 可选选择   | 使用条件                                   | 官方来源                          |
| ----------- | ---------- | ------------------------------------------ | --------------------------------- |
| ORM         | SQLAlchemy | 需要 ORM 或复杂 SQL 映射时                 | <https://docs.sqlalchemy.org/>    |
| 迁移        | Alembic    | 使用 SQLAlchemy 且需要 schema migration 时 | <https://alembic.sqlalchemy.org/> |
| HTTP client | HTTPX      | 后端需要请求其他 HTTP 服务时               | <https://www.python-httpx.org/>   |

## 不作为默认推荐

| 库     | 规则                                     |
| ------ | ---------------------------------------- |
| Django | 只有用户明确要求或既有项目已使用时才沿用 |
| Flask  | 只有用户明确要求或既有项目已使用时才沿用 |
