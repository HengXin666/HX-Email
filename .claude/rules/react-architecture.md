# React TS 架构规则 (按需加载)

## 功能优先 (Feature-Based), 非文件类型分组
- ❌ 按类型分: components/ hooks/ services/ utils/ — 改一个功能要跳5个目录。
- ✅ 按功能分: features/auth/ 内含 components/ hooks/ api/ types/ — 一个功能一个文件夹。
- 参考: Bulletproof React (alan2207), Vercel Style Guide, Feature-Sliced Design。

## 门面 (index.ts barrel)
    // features/auth/index.ts — 公共 API 面
    export { LoginPage } from "./LoginPage";
    export { useAuth } from "./hooks/useAuth";
    export type { AuthUser } from "./types";
调用方: import { LoginPage, useAuth } from "@/features/auth"。
未从 index.ts 导出的文件 = 私有实现, 外部不可引用 (ESLint no-restricted-imports 可强制)。

## 功能内结构
    features/auth/
      index.ts              # 公共 API (barrel), 只导出外部需要的
      LoginPage.tsx         # 页面级组件
      components/           # 功能内 UI 组件 (私有, 不对外导出)
      hooks/                # 功能内 hooks (私有或选择性导出)
      api/                  # API 调用 (私有)
      types.ts              # 功能内类型 (选择性导出)

## 拆分触发
- .tsx/.ts 文件 >300 行 -> 拆子组件或抽 hook/工具函数。
  (ESLint max-lines 默认 300; 业界共识 200-400, TypeScript/JSX 偏冗长可放宽至 400)
- 组件 >250 行 -> 优先考虑拆分。
- 功能目录下文件 >10 -> 检查是否有子功能可独立成新 feature。

## 组件内部顺序 (Vercel / Airbnb 共识)
    export function UserProfile({ userId }: UserProfileProps) {
      // 1. Hooks (useState, useContext, custom hooks)
      // 2. Derived values (useMemo)
      // 3. Side effects (useEffect)
      // 4. Event handlers
      // 5. Early returns (loading / error / empty)
      // 6. Main return (JSX)
    }

## 状态分层
- 服务端状态 -> TanStack Query / SWR (缓存、重取、乐观更新)
- 功能内状态 -> feature 内 useState/useReducer
- 跨功能共享 -> Context 或全局 store (Zustand 等)
- 展示组件 (components/ui/): 纯渲染, 只接 props, 无副作用
- 原则: 状态尽量留在本地, 不要过早提升。
