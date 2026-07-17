# React TS 命名与类型规则 (按需加载)

## 类型安全 (强制)
- tsconfig strict: true (涵盖 noImplicitAny / strictNullChecks / noUncheckedIndexedAccess 等)。
- 禁止 `any` (eslint no-explicit-any: error)。
  例外: 第三方库类型缺失时 `// eslint-disable-next-line no-explicit-any` + 注明原因。
- OK: `function parse(raw: string): Record<string, number> { ... }`
- NG: `function parse(raw: any): any { ... }`
- unknown > any: 真不确定类型用 `unknown`, 使用前 narrowing 或类型守卫。
- 类型守卫优先于类型断言: `if (typeof x === "string")` 而非 `x as string`。
- 异步状态用 discriminated union (业界共识):
    type AsyncState<T> =
      | { status: "idle" }
      | { status: "loading" }
      | { status: "success"; data: T }
      | { status: "error"; error: string };

## interface vs type (Vercel / Google 共识)
- 对象形状用 interface (可扩展、可合并声明)
- 联合类型/交叉类型/映射类型用 type
- 禁止 `I` 前缀 (interface IUserProps) — Google Style Guide 明确反对
- Props 接口以 Props 结尾: `UserProfileProps`, `ButtonProps`

## 命名约定
- 组件: PascalCase (`Dashboard`, `UserList`); 文件名 = 组件名。
- Hook: use 前缀 + camelCase (`useAuth`, `useDebounce`)。
- 函数/变量/属性: camelCase (`fetchUsers`, `isLoading`)。
- 布尔值: is/has/can/should 前缀 (`isLoading`, `hasError`, `canEdit`)。
- 常量: UPPER_SNAKE_CASE (`MAX_RETRY`, `API_BASE_URL`)。
- 类型/接口: PascalCase, 枚举值 PascalCase。
- 事件处理: handle 前缀 (`handleClick`, `handleSubmit`)。
- 回调 props: on 前缀 (`onClick`, `onSubmit`)。
- 目录: kebab-case (`feature-auth/`, `user-profile/`), 除非框架强制 (Next.js App Router)。

## 中文命名 (双重拦截)
- tsc + eslint 拦截中文/非 ASCII 标识符。
- 允许: 中文注释、中文字符串字面量。禁止: 中文变量/函数/组件/参数/文件名。
- 发现中文命名 -> 视为 AI 幻觉, 立即改英文。

## 导出规则
- 一律 named export (`export function Button`), 不写 `export default`。
- 例外: Next.js page.tsx / React.lazy() 动态导入 — 框架强制 default export 时允许。
- 原因: named export 重构安全 (IDE 自动改名)、tree-shaking 友好、禁止导入时随意重命名。
  业界佐证: Vercel Style Guide, MetaMask (主动迁移 default→named), Airbnb TS。
- barrel (index.ts): 只 re-export 公共 API, 未导出 = 私有。
- 禁止 `export *` — 不可控, 易泄露实现细节。

## 路径别名 (强制)
- tsconfig paths 配置 `@/` 映射 `src/`, 禁止 `../../../` 深层相对路径:
    // tsconfig.json
    { "compilerOptions": { "paths": { "@/*": ["./src/*"] } } }
- 子别名按需: `@features/*`, `@components/*`, `@hooks/*`, `@utils/*`。

## 常量 / 通用方法 / 类型
- 魔法值 -> `src/config/const.ts` 或 `src/constants/<业务>.ts`。
- 跨功能纯函数 -> `src/utils/<功能>.ts`。
- 全局类型 -> `src/types/` (按域拆分), 功能内类型 -> feature 内 `types.ts`。
- 禁止 enum (TypeScript enum 有 JS 运行时开销) — Vercel Style Guide 明确推荐 `as const`:
    // ✅ const object + as const
    export const STATUS = { IDLE: "idle", LOADING: "loading" } as const;
    export type Status = (typeof STATUS)[keyof typeof STATUS];
