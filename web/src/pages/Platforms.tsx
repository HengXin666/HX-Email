import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  IconEdit,
  IconLink,
  IconPlus,
  IconSearch,
  IconServer,
  IconShield,
  IconTrash,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge, Button, Card, Input, Modal, Select } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { BindingStatus, Platform, PlatformBinding, UsableEmail } from "../types";
import { PlatformCreateModal } from "./impl/PlatformCreateModal";
import { PlatformLogo } from "./impl/PlatformLogo";

type PlatformEmailBinding = PlatformBinding & { email: UsableEmail };

export const Platforms: React.FC = () => {
  const {
    platforms,
    emails,
    createPlatform,
    updatePlatform,
    deletePlatform,
    createEmail,
    refreshEmails,
    refreshPlatforms,
  } = useApp();
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showAddEmail, setShowAddEmail] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedPlatformId, setSelectedPlatformId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [bindingsByPlatform, setBindingsByPlatform] = useState<
    Record<number, PlatformEmailBinding[]>
  >({});

  const filtered = useMemo(
    () =>
      platforms.filter((p) => (!query ? true : p.name.toLowerCase().includes(query.toLowerCase()))),
    [platforms, query],
  );

  const selected = platforms.find((p) => p.id === selectedPlatformId);
  const refreshBindingMap = useCallback(async (): Promise<void> => {
    const entries = await Promise.all(
      emails.map(async (email) => {
        try {
          const bindings = await api.listBindings(email.id);
          return { email, bindings };
        } catch {
          return { email, bindings: [] as PlatformBinding[] };
        }
      }),
    );
    const next: Record<number, PlatformEmailBinding[]> = {};
    entries.forEach(({ email, bindings }) => {
      bindings.forEach((binding) => {
        const platformId = binding.platform.id;
        next[platformId] = [...(next[platformId] || []), { ...binding, email }];
      });
    });
    setBindingsByPlatform((current) => {
      const merged: Record<number, PlatformEmailBinding[]> = { ...next };
      Object.entries(current).forEach(([platformId, bindings]) => {
        const id = Number(platformId);
        const known = new Set((merged[id] || []).map((binding) => binding.id));
        const missing = bindings.filter((binding) => !known.has(binding.id));
        if (missing.length > 0) merged[id] = [...(merged[id] || []), ...missing];
      });
      return merged;
    });
  }, [emails]);

  useEffect(() => {
    void refreshBindingMap();
  }, [refreshBindingMap]);

  const selectedBindings = useMemo(
    () => (selected ? bindingsByPlatform[selected.id] || [] : []),
    [bindingsByPlatform, selected],
  );
  const bindingCounts = useMemo(() => {
    const counts: Record<number, number> = {};
    platforms.forEach((platform) => {
      counts[platform.id] = bindingsByPlatform[platform.id]?.length || platform.binding_count || 0;
    });
    return counts;
  }, [bindingsByPlatform, platforms]);

  const handleCreate = async (name: string): Promise<void> => {
    await createPlatform(name);
  };

  const handleUpdate = async (): Promise<void> => {
    if (!editingId || !editName.trim()) return;
    try {
      await updatePlatform(editingId, editName.trim());
      toast("平台已更新", "success");
      setEditingId(null);
      setEditName("");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "平台更新失败", "error");
    }
  };

  const handleDelete = async (id: number): Promise<void> => {
    if (!confirm("确定删除该平台？")) return;
    try {
      await deletePlatform(id);
      toast("平台已删除", "success");
      if (selectedPlatformId === id) setSelectedPlatformId(null);
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "平台删除失败", "error");
    }
  };

  const handleAddEmailToPlatform = async (payload: AddPlatformEmailPayload): Promise<void> => {
    if (!selected) return;
    const newAddress = payload.address.trim();
    try {
      let usableEmail: UsableEmail | undefined;
      if (newAddress) {
        usableEmail =
          emails.find((email) => email.address.toLowerCase() === newAddress.toLowerCase()) ||
          (await createEmail(newAddress, payload.label.trim() || newAddress));
      } else if (payload.usableEmailId !== null) {
        usableEmail = emails.find((email) => email.id === payload.usableEmailId);
      }
      if (!usableEmail) return;
      const binding = await api.createBinding(
        usableEmail.id,
        selected.id,
        payload.status,
        payload.notes.trim(),
      );
      setBindingsByPlatform((current) => {
        const platformBindings = current[selected.id] || [];
        if (platformBindings.some((item) => item.id === binding.id)) return current;
        return {
          ...current,
          [selected.id]: [...platformBindings, { ...binding, email: usableEmail }],
        };
      });
      await Promise.all([refreshEmails(), refreshPlatforms()]);
      toast("邮箱已添加到平台", "success");
      setShowAddEmail(false);
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "添加邮箱失败", "error");
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="平台绑定"
        subtitle="管理平台目录、可用邮箱绑定关系和验证状态"
        actions={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={14} /> 新建平台
          </Button>
        }
      />

      <div className="flex-1 flex min-h-0">
        {/* 左：平台列表 */}
        <div className="w-80 shrink-0 h-full border-r border-gh-border bg-gh-canvas flex flex-col">
          <div className="px-3 py-3 border-b border-gh-border">
            <div className="relative">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索平台..."
                className="w-full bg-gh-canvas-inset border border-gh-border rounded-md pl-8 pr-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
              />
              <IconSearch
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gh-text-secondary"
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <AnimatePresence>
              {filtered.map((p) => (
                <motion.div
                  key={p.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <Card
                    selected={selectedPlatformId === p.id}
                    onClick={() => setSelectedPlatformId(p.id)}
                    className="p-3"
                  >
                    <div className="flex items-start gap-3">
                      <PlatformLogo name={p.name} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gh-text truncate">{p.name}</div>
                        <div className="text-xs text-gh-text-secondary mt-0.5">
                          {bindingCounts[p.id] || 0} 个邮箱绑定
                        </div>
                      </div>
                    </div>
                    <div
                      className="flex gap-1 mt-2 pt-2 border-t border-gh-border/60"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingId(p.id);
                          setEditName(p.name);
                        }}
                      >
                        <IconEdit size={12} /> 编辑
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(p.id)}>
                        <IconTrash size={12} /> 删除
                      </Button>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </AnimatePresence>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-sm text-gh-text-secondary">暂无平台</div>
            )}
          </div>
        </div>

        {/* 右：平台详情 */}
        <div className="flex-1 flex flex-col min-w-0 h-full">
          {!selected ? (
            <div className="flex-1 flex items-center justify-center text-gh-text-secondary text-sm">
              <div className="text-center">
                <IconServer size={48} className="mx-auto mb-3 opacity-30" />
                <div>选择一个平台查看详情</div>
              </div>
            </div>
          ) : (
            <motion.div
              key={selected.id}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex-1 flex flex-col"
            >
              <div className="px-6 py-5 border-b border-gh-border bg-gradient-to-r from-gh-canvas-subtle to-gh-canvas">
                <div className="flex items-center gap-4">
                  <PlatformLogo
                    name={selected.name}
                    size="lg"
                    className="shadow-lg shadow-black/20"
                  />
                  <div>
                    <h2 className="text-xl font-bold text-gh-text">{selected.name}</h2>
                    <div className="text-sm text-gh-text-secondary mt-1">
                      {bindingCounts[selected.id] || 0} 个绑定
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-auto p-6">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2">
                    <IconShield size={14} /> 绑定的邮箱
                  </h3>
                  <Button size="sm" variant="secondary" onClick={() => setShowAddEmail(true)}>
                    <IconPlus size={12} /> 添加邮箱
                  </Button>
                </div>
                <div className="space-y-2">
                  {selectedBindings.length === 0 ? (
                    <div className="text-center py-12 text-sm text-gh-text-secondary">
                      暂无邮箱绑定到此平台
                      <div className="mt-2">
                        <Button size="sm" variant="ghost" onClick={() => setShowAddEmail(true)}>
                          <IconPlus size={12} /> 添加邮箱
                        </Button>
                      </div>
                    </div>
                  ) : (
                    selectedBindings.map((binding) => (
                      <div
                        key={binding.id}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gh-border bg-gh-canvas-subtle"
                      >
                        <div className="w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center">
                          <IconLink size={14} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gh-text truncate">
                            {binding.email.address}
                          </div>
                          {(binding.notes || binding.email.label) && (
                            <div className="text-xs text-gh-text-secondary truncate">
                              {binding.notes || binding.email.label}
                            </div>
                          )}
                        </div>
                        <Badge color="#3fb950">已绑定</Badge>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      <PlatformCreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreate={handleCreate}
        existingPlatforms={platforms}
      />

      <PlatformEmailModal
        open={showAddEmail}
        onClose={() => setShowAddEmail(false)}
        emails={emails}
        platform={selected}
        onSubmit={handleAddEmailToPlatform}
      />

      {/* Edit */}
      <Modal
        open={!!editingId}
        onClose={() => {
          setEditingId(null);
          setEditName("");
        }}
        title="编辑平台"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setEditingId(null);
                setEditName("");
              }}
            >
              取消
            </Button>
            <Button variant="primary" onClick={handleUpdate}>
              保存
            </Button>
          </>
        }
      >
        <div className="flex items-end gap-3">
          <PlatformLogo name={editName} />
          <div className="flex-1">
            <Input
              label="平台名称"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

interface AddPlatformEmailPayload {
  usableEmailId: number | null;
  address: string;
  label: string;
  status: BindingStatus;
  notes: string;
}

const BINDING_STATUS_OPTIONS: Array<{ value: BindingStatus; label: string }> = [
  { value: "active", label: "正常使用中" },
  { value: "pending_verification", label: "待验证" },
  { value: "risk", label: "有风险" },
  { value: "disabled", label: "不可用" },
  { value: "archived", label: "已归档" },
];

const PlatformEmailModal: React.FC<{
  open: boolean;
  onClose: () => void;
  emails: UsableEmail[];
  platform: Platform | undefined;
  onSubmit: (payload: AddPlatformEmailPayload) => Promise<void>;
}> = ({ open, onClose, emails, platform, onSubmit }) => {
  const [usableEmailId, setUsableEmailId] = useState<number | "">("");
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [status, setStatus] = useState<BindingStatus>("active");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setUsableEmailId("");
    setAddress("");
    setLabel("");
    setStatus("active");
    setNotes("");
  }, [open]);

  const canSubmit = Boolean(address.trim() || usableEmailId);

  const handleSubmit = async (): Promise<void> => {
    if (!canSubmit) return;
    setLoading(true);
    try {
      await onSubmit({
        usableEmailId: usableEmailId === "" ? null : usableEmailId,
        address,
        label,
        status,
        notes,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="添加邮箱到平台"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={!canSubmit}>
            添加
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {platform && (
          <div className="flex items-center gap-2 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
            <PlatformLogo name={platform.name} size="sm" />
            <div className="text-sm font-medium text-gh-text truncate">{platform.name}</div>
          </div>
        )}
        <Select
          id="platform-existing-email"
          label="已有邮箱"
          value={usableEmailId}
          onChange={(value) => setUsableEmailId(value ? Number(value) : "")}
          options={[
            { value: "", label: "不选择" },
            ...emails.map((email) => ({ value: email.id, label: email.address })),
          ]}
        />
        <Input
          label="新邮箱地址"
          type="email"
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          placeholder="owner+site@example.com"
        />
        <Input
          label="备注名称"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="GitHub login"
        />
        <Select
          id="platform-binding-status"
          label="绑定状态"
          value={status}
          onChange={(value) => setStatus(value as BindingStatus)}
          options={BINDING_STATUS_OPTIONS}
        />
        <div>
          <label className="text-xs font-medium text-gh-text-muted block mb-1.5">绑定备注</label>
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={3}
            className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent resize-y"
          />
        </div>
      </div>
    </Modal>
  );
};
