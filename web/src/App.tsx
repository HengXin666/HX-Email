import { Mail, ShieldCheck } from "lucide-react";

import { Button } from "./components/ui/button";

type UsableEmail = {
  id: number;
  address: string;
  label: string;
  kind: "primary" | "alias" | "temp" | "custom";
  status: "active" | "inactive" | "archived";
  group?: { id: number; name: string; color: string } | null;
  tags?: { id: number; name: string; color: string }[];
  platformBindingCount?: number;
};

type Session = {
  username: string;
  usableEmails: UsableEmail[];
  page?: number;
  pageSize?: number;
  total?: number;
};

type AppProps = {
  registrationEnabled?: boolean;
  session?: Session;
};

const kindLabels: Record<UsableEmail["kind"], string> = {
  primary: "主邮箱地址",
  alias: "别名邮箱地址",
  temp: "临时邮箱地址",
  custom: "可用邮箱",
};

const statusLabels: Record<UsableEmail["status"], string> = {
  active: "可用",
  inactive: "已停用",
  archived: "已归档",
};

function Workbench({ session }: { session: Session }) {
  const total = session.total ?? session.usableEmails.length;
  const page = session.page ?? 1;
  return (
    <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 md:flex-row md:items-end">
          <div>
            <p className="text-sm text-emerald-200/80">{session.username}</p>
            <h1 className="mt-1 text-2xl font-semibold text-white">可用邮箱工作台</h1>
          </div>
          <Button type="button">
            <Mail size={16} />
            添加邮箱账号
          </Button>
        </header>

        <div className="grid gap-3 rounded-lg border border-white/10 bg-slate-900 p-3 md:grid-cols-[1.5fr_repeat(3,1fr)]">
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">关键词</span>
            <input
              aria-label="关键词"
              className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-white outline-none focus:border-emerald-300"
              placeholder="地址或标签"
              type="search"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">类型</span>
            <select
              aria-label="类型"
              className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-white outline-none focus:border-emerald-300"
            >
              <option>全部类型</option>
              <option>主邮箱地址</option>
              <option>别名邮箱地址</option>
              <option>临时邮箱地址</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">状态</span>
            <select
              aria-label="状态"
              className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-white outline-none focus:border-emerald-300"
            >
              <option>全部状态</option>
              <option>可用</option>
              <option>已停用</option>
              <option>已归档</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">平台绑定</span>
            <select
              aria-label="平台绑定"
              className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-white outline-none focus:border-emerald-300"
            >
              <option>全部绑定</option>
              <option>未绑定平台</option>
              <option>已绑定平台</option>
            </select>
          </label>
        </div>

        <div className="overflow-hidden rounded-lg border border-white/10 bg-slate-900">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">地址</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">标签</th>
                <th className="px-4 py-3 font-medium">分组</th>
                <th className="px-4 py-3 font-medium">平台绑定</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {session.usableEmails.map((usableEmail) => (
                <tr className="border-t border-white/10" key={usableEmail.id}>
                  <td className="px-4 py-4 font-medium text-white">{usableEmail.address}</td>
                  <td className="px-4 py-4 text-slate-300">{kindLabels[usableEmail.kind]}</td>
                  <td className="px-4 py-4 text-slate-300">
                    <div>{usableEmail.label}</div>
                    {usableEmail.tags?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {usableEmail.tags.map((tag) => (
                          <span
                            className="rounded border border-white/10 px-2 py-0.5 text-xs"
                            key={tag.id}
                            style={{ color: tag.color }}
                          >
                            {tag.name}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-4 text-slate-300">
                    {usableEmail.group ? (
                      <span className="inline-flex items-center gap-2">
                        <span
                          className="size-2 rounded-full"
                          style={{ backgroundColor: usableEmail.group.color }}
                        />
                        {usableEmail.group.name}
                      </span>
                    ) : (
                      "未分组"
                    )}
                  </td>
                  <td className="px-4 py-4 text-slate-300">
                    {(usableEmail.platformBindingCount ?? 0) > 0
                      ? `${usableEmail.platformBindingCount} 个平台`
                      : "未绑定平台"}
                  </td>
                  <td className="px-4 py-4 text-slate-300">{statusLabels[usableEmail.status]}</td>
                  <td className="px-4 py-4 text-right">
                    <Button disabled={usableEmail.status !== "active"} type="button">
                      停用
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <footer className="flex items-center justify-between text-sm text-slate-400">
          <span>{`第 ${page} 页 / 共 ${total} 条`}</span>
          <div className="flex gap-2">
            <Button disabled={page <= 1} type="button">
              上一页
            </Button>
            <Button disabled={total <= page * (session.pageSize ?? 50)} type="button">
              下一页
            </Button>
          </div>
        </footer>
      </section>
    </main>
  );
}

export function App({ registrationEnabled = false, session }: AppProps) {
  document.documentElement.classList.add("dark");

  if (session) {
    return <Workbench session={session} />;
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_20%_20%,rgba(45,212,191,0.16),transparent_34%),linear-gradient(135deg,#08111f_0%,#121827_45%,#06141a_100%)] px-4 py-8 text-foreground">
      <section className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center">
        <div className="relative grid w-full max-w-4xl grid-cols-1 items-center gap-0 md:grid-cols-[1fr_0.92fr]">
          <form className="z-10 flex min-h-[520px] flex-col justify-center rounded-lg border border-white/15 bg-slate-950/70 px-8 py-10 shadow-2xl shadow-black/40 backdrop-blur-xl md:px-14">
            <div className="mb-8">
              <p className="text-sm text-emerald-200/80">欢迎回来</p>
              <h1 className="mt-2 text-3xl font-semibold text-white">HX Email</h1>
              <p className="mt-2 text-sm text-slate-300">
                登录后管理可用邮箱、验证码读取和平台绑定。
              </p>
            </div>

            <label className="mb-6 block">
              <span className="mb-2 block text-sm font-medium text-slate-200">
                用户名
              </span>
              <input
                aria-label="用户名"
                className="h-11 w-full rounded-md border border-slate-500/70 bg-transparent px-3 text-base text-white outline-none transition focus:border-emerald-200"
                placeholder="用户名"
                type="text"
              />
            </label>

            <label className="mb-8 block">
              <span className="mb-2 block text-sm font-medium text-slate-200">
                密码
              </span>
              <input
                aria-label="密码"
                className="h-11 w-full rounded-md border border-slate-500/70 bg-transparent px-3 text-base text-white outline-none transition focus:border-emerald-200"
                placeholder="密码"
                type="password"
              />
            </label>

            <Button className="w-full" type="button">
              <ShieldCheck size={16} />
              登录
            </Button>

            {registrationEnabled ? (
              <div className="mt-8 border-t border-white/10 pt-7">
                <h2 className="text-lg font-semibold text-white">注册 HX Email</h2>
                <p className="mt-1 text-sm text-slate-300">
                  创建本地用户后会进入独立的数据空间。
                </p>
                <label className="mt-5 block">
                  <span className="mb-2 block text-sm font-medium text-slate-200">
                    新用户名
                  </span>
                  <input
                    aria-label="新用户名"
                    className="h-11 w-full rounded-md border border-slate-500/70 bg-transparent px-3 text-base text-white outline-none transition focus:border-emerald-200"
                    placeholder="新用户名"
                    type="text"
                  />
                </label>
                <label className="mt-4 block">
                  <span className="mb-2 block text-sm font-medium text-slate-200">
                    新密码
                  </span>
                  <input
                    aria-label="新密码"
                    className="h-11 w-full rounded-md border border-slate-500/70 bg-transparent px-3 text-base text-white outline-none transition focus:border-emerald-200"
                    placeholder="新密码"
                    type="password"
                  />
                </label>
                <Button className="mt-5 w-full" type="button">
                  注册
                </Button>
              </div>
            ) : null}
          </form>

          <aside className="relative z-20 -mt-6 min-h-[360px] rounded-lg border border-emerald-200/25 bg-[linear-gradient(145deg,rgba(236,253,245,0.96),rgba(187,247,208,0.92))] p-8 text-slate-950 shadow-xl shadow-emerald-950/30 md:-ml-8 md:mt-0">
            <div className="mb-10 flex items-center gap-3">
              <span className="flex size-11 items-center justify-center rounded-md bg-slate-950 text-emerald-200">
                <Mail size={22} />
              </span>
              <div>
                <p className="text-2xl font-semibold">HX Email</p>
                <p className="text-sm text-slate-700">重写工作台</p>
              </div>
            </div>
            <p className="text-base leading-7 text-slate-800">
              以旧版 outlookEmailPlus 的邮箱管理能力为参考，新的骨架将后端、
              前端、配置和迁移入口拆成稳定的垂直切片。
            </p>
          </aside>
        </div>
      </section>
    </main>
  );
}
