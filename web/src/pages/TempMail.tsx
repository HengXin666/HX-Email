import { AnimatePresence, motion } from "framer-motion";
import React, { useMemo, useState } from "react";
import { api } from "../api/client";
import {
  IconArchive,
  IconCheck,
  IconClock,
  IconCopy,
  IconKey,
  IconLink,
  IconMail,
  IconPlus,
  IconRefresh,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge, Button, Card, Input, Modal } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { TempMessage } from "../types";

export const TempMail: React.FC = () => {
  const { emails, createTempMail, refreshEmails } = useApp();
  const { toast } = useToast();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState(false);

  const temps = useMemo(
    () => emails.filter((e) => e.kind === "temp" && e.status !== "archived"),
    [emails],
  );
  const selected = temps.find((e) => e.id === selectedId);

  const handleCreate = async () => {
    setLoading(true);
    try {
      const e = await createTempMail(newLabel || "临时邮箱");
      toast("临时邮箱已创建", "success");
      setNewLabel("");
      setShowCreate(false);
      setSelectedId(e.id);
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleArchive = async (id: number) => {
    if (!confirm("确定归档该临时邮箱？")) return;
    try {
      await api.archiveTempMail(id);
      await refreshEmails();
      toast("已归档", "success");
      if (selectedId === id) setSelectedId(null);
    } catch (err: any) {
      toast(err.message, "error");
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="临时邮箱"
        subtitle="基于 Cloudflare 的临时邮箱服务，用于快速注册"
        actions={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={14} /> 创建临时邮箱
          </Button>
        }
      />

      <div className="flex-1 flex min-h-0">
        {/* 左：列表 */}
        <div className="w-80 shrink-0 h-full border-r border-gh-border bg-gh-canvas flex flex-col">
          <div className="h-12 px-3 flex items-center border-b border-gh-border">
            <span className="text-sm font-semibold text-gh-text">
              我的临时邮箱 <span className="text-gh-text-secondary">{temps.length}</span>
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <AnimatePresence>
              {temps.map((e) => (
                <motion.div
                  key={e.id}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <Card
                    selected={selectedId === e.id}
                    onClick={() => setSelectedId(e.id)}
                    className="p-3"
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="w-9 h-9 rounded-lg bg-gh-orange/10 text-gh-orange flex items-center justify-center shrink-0">
                        <IconClock size={16} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gh-text truncate">{e.label}</div>
                        <div className="text-xs text-gh-text-muted font-mono truncate mt-0.5">
                          {e.address}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-gh-border/60">
                      <span className="text-[11px] text-gh-text-secondary">{e.updated_at}</span>
                      <button
                        onClick={(ev) => {
                          ev.stopPropagation();
                          handleArchive(e.id);
                        }}
                        className="p-1 rounded-md text-gh-text-muted hover:text-gh-danger hover:bg-gh-danger/10 transition-colors"
                        title="归档"
                      >
                        <IconArchive size={13} />
                      </button>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </AnimatePresence>
            {temps.length === 0 && (
              <div className="text-center py-12 text-sm text-gh-text-secondary">暂无临时邮箱</div>
            )}
          </div>
        </div>

        {/* 右：详情 */}
        <div className="flex-1 flex flex-col min-w-0 h-full">
          {!selected ? (
            <div className="flex-1 flex items-center justify-center text-gh-text-secondary text-sm">
              <div className="text-center">
                <IconClock size={48} className="mx-auto mb-3 opacity-30" />
                <div>选择一个临时邮箱查看邮件</div>
              </div>
            </div>
          ) : (
            <TempDetail
              key={selected.id}
              emailId={selected.id}
              address={selected.address}
              label={selected.label}
            />
          )}
        </div>
      </div>

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="创建临时邮箱"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={handleCreate} loading={loading}>
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="px-3 py-2 rounded-md bg-gh-accent/10 border border-gh-accent/30 text-xs text-gh-accent">
            <IconClock size={12} className="inline mr-1" />
            邮箱地址将自动生成，也可指定自定义地址
          </div>
          <Input
            label="备注名称"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="例如：GitHub 注册用"
          />
        </div>
      </Modal>
    </div>
  );
};

const TempDetail: React.FC<{ emailId: number; address: string; label: string }> = ({
  emailId,
  address,
  label,
}) => {
  const { toast } = useToast();
  const [messages, setMessages] = useState<TempMessage[]>([]);
  const [codes, setCodes] = useState<Array<{ message_id: string; code: string }>>([]);
  const [links, setLinks] = useState<Array<{ message_id: string; url: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [m, c, l] = await Promise.all([
        api.tempMessages(emailId),
        api.tempCodes(emailId),
        api.tempLinks(emailId),
      ]);
      setMessages(m);
      setCodes(c);
      setLinks(l);
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailId]);

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    toast("已复制邮箱地址", "success");
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-gh-border bg-gradient-to-r from-gh-canvas-subtle to-gh-canvas">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gh-orange/10 text-gh-orange flex items-center justify-center shadow-lg shadow-gh-orange/20">
            <IconClock size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-lg font-semibold text-gh-text truncate">{label}</div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm font-mono text-gh-text-muted truncate">{address}</span>
              <button
                onClick={handleCopy}
                className="p-1 rounded text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
              >
                {copied ? (
                  <IconCheck size={13} className="text-gh-success" />
                ) : (
                  <IconCopy size={13} />
                )}
              </button>
            </div>
          </div>
          <Button variant="secondary" onClick={load} loading={loading}>
            <IconRefresh size={13} /> 刷新
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* Quick stats */}
        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="rounded-lg border border-gh-border bg-gh-canvas-subtle p-3">
            <div className="flex items-center gap-2 text-gh-text-secondary text-xs mb-1">
              <IconMail size={12} /> 邮件
            </div>
            <div className="text-2xl font-bold text-gh-text tabular-nums">{messages.length}</div>
          </div>
          <div className="rounded-lg border border-gh-border bg-gh-canvas-subtle p-3">
            <div className="flex items-center gap-2 text-gh-text-secondary text-xs mb-1">
              <IconKey size={12} /> 验证码
            </div>
            <div className="text-2xl font-bold text-gh-success tabular-nums">{codes.length}</div>
          </div>
          <div className="rounded-lg border border-gh-border bg-gh-canvas-subtle p-3">
            <div className="flex items-center gap-2 text-gh-text-secondary text-xs mb-1">
              <IconLink size={12} /> 验证链接
            </div>
            <div className="text-2xl font-bold text-gh-accent tabular-nums">{links.length}</div>
          </div>
        </div>

        {codes.length > 0 && (
          <div className="mb-5">
            <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-2">
              最新验证码
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {codes.slice(0, 4).map((c) => (
                <button
                  key={c.message_id}
                  onClick={() => {
                    navigator.clipboard.writeText(c.code);
                    toast("已复制", "success");
                  }}
                  className="px-4 py-3 rounded-lg border border-gh-border bg-gradient-to-br from-gh-success/5 to-gh-canvas-subtle hover:border-gh-success/50 transition-all text-left pulse-ring"
                >
                  <div className="text-xs text-gh-success mb-0.5 flex items-center gap-1">
                    <IconKey size={10} /> CODE
                  </div>
                  <div className="text-2xl font-mono font-bold text-gh-success tracking-widest">
                    {c.code}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-2">
          收件箱 ({messages.length})
        </h4>
        <div className="space-y-2">
          {messages.length === 0 ? (
            <div className="text-center py-12 text-sm text-gh-text-secondary">
              等待新邮件...
              <div className="mt-2 text-xs">每 15 秒自动刷新</div>
            </div>
          ) : (
            messages.map((m, i) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="rounded-lg border border-gh-border bg-gh-canvas-subtle p-3 hover:border-gh-text-muted transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center shrink-0">
                    <IconMail size={14} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <div className="text-sm font-medium text-gh-text truncate">{m.subject}</div>
                      {m.received_at && (
                        <span className="text-[11px] text-gh-text-secondary whitespace-nowrap">
                          {m.received_at}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gh-text-muted truncate">{m.from_address}</div>
                    {m.text && (
                      <div className="mt-2 text-xs text-gh-text-secondary font-mono bg-gh-canvas-inset p-2 rounded whitespace-pre-wrap break-all">
                        {m.text}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </motion.div>
  );
};
