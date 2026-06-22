# HX Email 重写 GitHub Issue 拆分草案

以下拆分遵循 tracer bullet：每个 issue 都应交付一条可验证的端到端路径，覆盖必要的 schema、API、UI 和测试。

发布到 GitHub 前需要确认粒度和依赖关系。确认后使用 `ready-for-agent` label。

## 1. 搭建重写项目骨架

**Title**: 搭建 FastAPI + uv 与 React + shadcn/ui 重写骨架

**Blocked by**: None

**User stories covered**: 开发者可以启动后端、前端和测试，为后续核心功能提供稳定入口。

## 2. 本地多用户与管理员注册开关

**Title**: 实现本地多用户登录、管理员初始化和注册开关

**Blocked by**: 1

**User stories covered**: 管理员可用 env 初始账号登录，开启/关闭注册；普通用户登录后只能进入自己的数据空间。

## 3. 邮箱账号添加与主可用邮箱

**Title**: 添加邮箱账号时创建主可用邮箱

**Blocked by**: 2

**User stories covered**: 用户可添加 Outlook/IMAP 邮箱账号，并在可用邮箱工作台看到主邮箱地址。

## 4. 真实别名邮箱管理

**Title**: 为邮箱账号管理真实别名邮箱地址

**Blocked by**: 3

**User stories covered**: 用户可为邮箱账号添加、停用和查看已在服务商后台配置好的别名邮箱地址。

## 5. 可用邮箱工作台、分组和标签

**Title**: 建立可用邮箱工作台并沿用分组标签筛选

**Blocked by**: 4

**User stories covered**: 用户可按类型、状态、分组、标签、平台和关键词筛选主邮箱、别名邮箱和临时邮箱。

## 6. CF 临时邮箱作为可用邮箱

**GitHub**: #6

**Title**: 接入 CF 临时邮箱并纳入可用邮箱工作台

**Blocked by**: 5

**User stories covered**: 用户可创建和读取 CF 临时邮箱，并像筛选其他可用邮箱一样筛选临时邮箱。

## 7. 按可用邮箱读取验证码

**GitHub**: #7

**Title**: 按可用邮箱收件地址读取验证码和验证链接

**Blocked by**: 5

**User stories covered**: 用户可从主邮箱或别名邮箱读取验证码，系统不会返回同一账号下其他地址收到的验证码。

## 8. 平台与平台绑定

**GitHub**: #8

**Title**: 管理平台并将平台绑定到可用邮箱

**Blocked by**: 5

**User stories covered**: 用户可创建平台，将可用邮箱绑定到平台，并维护绑定状态和备注。

## 9. 以可用邮箱为单位的邮箱池

**Title**: 将邮箱池领取状态迁移到可用邮箱

**Blocked by**: 6, 7

**User stories covered**: 用户可领取主邮箱、别名邮箱或 CF 临时邮箱，完成注册任务并记录结果。

## 10. 导入导出与旧核心能力回归

**Title**: 补齐导入导出和旧项目核心回归能力

**Blocked by**: 9

**User stories covered**: 用户可迁移和备份核心数据，旧项目核心管理能力在新架构下保持可用。
