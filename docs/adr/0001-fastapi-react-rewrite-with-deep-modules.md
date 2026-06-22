# 使用 FastAPI 与 React 重写并采用深模块架构

本项目重写时选择 Python FastAPI 后端、uv 包管理、React + TypeScript + shadcn/ui + Tailwind 前端，并把核心业务组织为深模块：路由和页面保持薄层，复杂规则收敛在可用邮箱、邮箱账号、平台绑定、验证码读取、邮箱池和临时邮箱等领域模块内部。旧版 outlookEmailPlus 作为功能和行为参考，但不照搬 Flask controller/service/repository 的浅层分层；这样可以保留原有能力，同时让新增的别名邮箱地址和平台绑定通过“可用邮箱”模型扩展系统，而不是侵入每条旧功能链路。
