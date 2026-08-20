import React, { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import {
  IconDownload,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconUpload,
  IconZap,
} from "../../components/icons";
import { Badge, Button, Input, Modal, Select } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type {
  PlatformRule,
  PlatformRuleInput,
  PlatformScanItem,
  RuleMatchField,
  RuleMatchType,
} from "../../types";

const FIELD_OPTIONS: Array<{ value: RuleMatchField; label: string }> = [
  { value: "domain", label: "发件人域名" },
  { value: "from", label: "发件人邮箱" },
  { value: "subject", label: "主题" },
  { value: "body", label: "正文" },
];

const TYPE_OPTIONS: Array<{ value: RuleMatchType; label: string }> = [
  { value: "contains", label: "包含" },
  { value: "exact", label: "精确" },
  { value: "regex", label: "正则" },
];

const EMPTY_FORM: PlatformRuleInput = {
  name: "",
  match_field: "domain",
  match_type: "contains",
  patterns: [],
  platform_name: "",
  enabled: true,
};

function patternsOf(rule: PlatformRule): string[] {
  if (rule.patterns && rule.patterns.length > 0) return rule.patterns;
  return rule.pattern ? [rule.pattern] : [];
}

interface PlatformRecognitionModalProps {
  open: boolean;
  onClose: () => void;
  onAccepted: () => void;
}

export const PlatformRecognitionModal: React.FC<PlatformRecognitionModalProps> = ({
  open,
  onClose,
  onAccepted,
}) => {
  const { toast } = useToast();
  const [tab, setTab] = useState<"rules" | "scan">("rules");
  const [rules, setRules] = useState<PlatformRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<PlatformRuleInput>(EMPTY_FORM);
  const [patternText, setPatternText] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [items, setItems] = useState<PlatformScanItem[]>([]);
  const [accepting, setAccepting] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importStrategy, setImportStrategy] = useState<"skip" | "replace">("skip");
  const [importing, setImporting] = useState(false);

  const loadRules = useCallback(async () => {
    setLoadingRules(true);
    try {
      setRules(await api.listRules());
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "加载规则失败", "error");
    } finally {
      setLoadingRules(false);
    }
  }, [toast]);

  useEffect(() => {
    if (open) {
      setTab("rules");
      void loadRules();
    }
  }, [open, loadRules]);

  const resetForm = (): void => {
    setForm(EMPTY_FORM);
    setPatternText("");
    setEditingId(null);
    setShowForm(false);
  };

  const handleSaveRule = async (): Promise<void> => {
    const patterns = patternText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (patterns.length === 0 || !form.platform_name.trim()) {
      toast("请填写至少一个匹配模式与目标平台", "error");
      return;
    }
    setSaving(true);
    try {
      const payload = { ...form, patterns };
      if (editingId !== null) {
        await api.updateRule(editingId, payload);
        toast("规则已更新", "success");
      } else {
        await api.createRule(payload);
        toast("规则已创建", "success");
      }
      resetForm();
      await loadRules();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "保存规则失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (id: number): Promise<void> => {
    if (!window.confirm("确定删除该识别规则？")) return;
    try {
      await api.deleteRule(id);
      toast("规则已删除", "success");
      await loadRules();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "删除规则失败", "error");
    }
  };

  const handleExport = async (): Promise<void> => {
    try {
      const rulesJson = await api.exportRules();
      const blob = new Blob([JSON.stringify(rulesJson, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `platform-rules-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast(`已导出 ${rulesJson.length} 条规则`, "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "导出失败", "error");
    }
  };

  const handleImport = async (): Promise<void> => {
    let parsed: PlatformRuleInput[];
    try {
      const value = JSON.parse(importText);
      parsed = Array.isArray(value) ? value : Array.isArray(value?.rules) ? value.rules : [];
      if (parsed.length === 0) throw new Error("未解析到规则");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "导入内容不是有效 JSON", "error");
      return;
    }
    setImporting(true);
    try {
      const result = await api.importRules(parsed, importStrategy);
      toast(
        `导入完成：新增 ${result.imported} 条` +
          (result.skipped > 0 ? `，跳过 ${result.skipped} 条` : ""),
        "success",
      );
      setImportText("");
      setShowImport(false);
      await loadRules();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "导入失败", "error");
    } finally {
      setImporting(false);
    }
  };

  const handleScan = async (): Promise<void> => {
    setScanning(true);
    try {
      const result = await api.scanPlatforms();
      setItems(result);
      if (result.length === 0) {
        toast("未识别到平台（请先拉取邮件）", "info");
      }
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "识别失败", "error");
    } finally {
      setScanning(false);
    }
  };

  const handleAccept = async (item: PlatformScanItem): Promise<void> => {
    setAccepting(item.platform);
    try {
      const result = await api.acceptScan(item.platform, item.usable_email_ids);
      toast(
        `已纳入平台「${result.platform}」：新建 ${result.bindings_created} 条绑定` +
          (result.bindings_skipped > 0 ? `，跳过 ${result.bindings_skipped} 条重复` : ""),
        "success",
      );
      onAccepted();
      setItems((current) => current.filter((entry) => entry.platform !== item.platform));
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "纳入平台失败", "error");
    } finally {
      setAccepting(null);
    }
  };

  const handleAcceptAll = async (): Promise<void> => {
    for (const item of [...items]) {
      await handleAccept(item);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="平台智能识别"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            关闭
          </Button>
          {tab === "scan" && items.length > 0 && (
            <Button
              variant="primary"
              onClick={() => void handleAcceptAll()}
              loading={accepting !== null}
            >
              <IconZap size={14} /> 全部纳入平台
            </Button>
          )}
        </>
      }
    >
      <div className="flex items-center gap-1 border-b border-gh-border mb-4">
        {[
          { key: "rules", label: "识别规则" },
          { key: "scan", label: "一键识别" },
        ].map((entry) => (
          <button
            key={entry.key}
            type="button"
            onClick={() => setTab(entry.key as "rules" | "scan")}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === entry.key
                ? "border-gh-accent text-gh-accent"
                : "border-transparent text-gh-text-muted hover:text-gh-text"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === "rules" ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-gh-text-secondary">
              自定义规则优先匹配；一个平台可配多个域名/模式（每行一个），支持导入导出分享
            </p>
            <div className="flex items-center gap-1.5 shrink-0">
              <Button size="sm" variant="ghost" onClick={() => void handleExport()}>
                <IconDownload size={12} /> 导出
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowImport((value) => !value)}>
                <IconUpload size={12} /> 导入
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  resetForm();
                  setShowForm((value) => !value);
                }}
              >
                <IconPlus size={12} /> {showForm ? "收起" : "添加规则"}
              </Button>
            </div>
          </div>

          {showImport && (
            <div className="rounded-lg border border-gh-border bg-gh-canvas-inset p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Select
                  id="import-strategy"
                  label="导入策略"
                  value={importStrategy}
                  onChange={(value) => setImportStrategy(value as "skip" | "replace")}
                  options={[
                    { value: "skip", label: "跳过已存在" },
                    { value: "replace", label: "替换同名平台" },
                  ]}
                />
                <div className="flex-1" />
                <Button
                  size="sm"
                  variant="primary"
                  loading={importing}
                  onClick={() => void handleImport()}
                >
                  开始导入
                </Button>
              </div>
              <textarea
                value={importText}
                onChange={(event) => setImportText(event.target.value)}
                placeholder='粘贴规则 JSON，如 [{"platform_name":"MySite","match_field":"domain","match_type":"contains","patterns":["mysite.com"]}]'
                rows={4}
                className="w-full rounded-md border border-gh-border bg-gh-canvas px-2.5 py-2 text-xs font-mono text-gh-text placeholder:text-gh-text-muted outline-none focus:border-gh-accent"
              />
            </div>
          )}

          {showForm && (
            <div className="rounded-lg border border-gh-border bg-gh-canvas-inset p-3 grid grid-cols-2 gap-2">
              <Input
                label="规则名称"
                placeholder="如 GitHub 通知"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
              <Input
                label="目标平台"
                placeholder="如 GitHub"
                value={form.platform_name}
                onChange={(event) => setForm({ ...form, platform_name: event.target.value })}
              />
              <Select
                id="rule-field"
                label="匹配字段"
                value={form.match_field}
                onChange={(value) => setForm({ ...form, match_field: value as RuleMatchField })}
                options={FIELD_OPTIONS}
              />
              <Select
                id="rule-type"
                label="匹配方式"
                value={form.match_type}
                onChange={(value) => setForm({ ...form, match_type: value as RuleMatchType })}
                options={TYPE_OPTIONS}
              />
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gh-text-secondary mb-1.5">
                  匹配模式（每行一个；域名模式下包含匹配可覆盖其全部子域名）
                </label>
                <textarea
                  value={patternText}
                  onChange={(event) => setPatternText(event.target.value)}
                  placeholder={
                    form.match_type === "regex"
                      ? "noreply@github\\.com$\nno-reply@github\\.com$"
                      : "github.com\ngithubusercontent.com"
                  }
                  rows={3}
                  className="w-full rounded-md border border-gh-border bg-gh-canvas px-2.5 py-2 text-xs font-mono text-gh-text placeholder:text-gh-text-muted outline-none focus:border-gh-accent"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-gh-text-muted">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                  className="accent-gh-accent"
                />
                启用
              </label>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={resetForm}>
                  取消
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  loading={saving}
                  onClick={() => void handleSaveRule()}
                >
                  {editingId !== null ? "保存修改" : "创建规则"}
                </Button>
              </div>
            </div>
          )}

          {loadingRules ? (
            <div className="text-center py-8 text-sm text-gh-text-secondary">加载中...</div>
          ) : rules.length === 0 ? (
            <div className="text-center py-8 text-sm text-gh-text-secondary">
              暂无识别规则，添加规则后可一键识别历史邮件
            </div>
          ) : (
            <div className="space-y-2">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className="flex items-center gap-2 rounded-lg border border-gh-border bg-gh-canvas-subtle px-3 py-2"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gh-text truncate">
                        {rule.platform_name}
                      </span>
                      <Badge color={rule.enabled ? "#3fb950" : "#6e7681"}>
                        {rule.enabled ? "启用" : "停用"}
                      </Badge>
                    </div>
                    <div className="text-xs text-gh-text-secondary truncate">
                      {rule.name || "(未命名)"} ·{" "}
                      {FIELD_OPTIONS.find((o) => o.value === rule.match_field)?.label} ·{" "}
                      {TYPE_OPTIONS.find((o) => o.value === rule.match_type)?.label} ·{" "}
                      <span className="font-mono">{patternsOf(rule).join("、")}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="p-1.5 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40"
                    title="编辑规则"
                    onClick={() => {
                      setEditingId(rule.id);
                      setForm({
                        name: rule.name,
                        match_field: rule.match_field,
                        match_type: rule.match_type,
                        patterns: patternsOf(rule),
                        platform_name: rule.platform_name,
                        enabled: rule.enabled,
                      });
                      setPatternText(patternsOf(rule).join("\n"));
                      setShowForm(true);
                    }}
                  >
                    <IconRefresh size={13} />
                  </button>
                  <button
                    type="button"
                    className="p-1.5 rounded-md text-gh-text-muted hover:text-gh-danger hover:bg-gh-danger/10"
                    title="删除规则"
                    onClick={() => void handleDeleteRule(rule.id)}
                  >
                    <IconTrash size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gh-text-secondary">
              扫描全部历史邮件的发件人，按规则/域名聚合出平台候选，确认后纳入平台目录并绑定对应邮箱
            </p>
            <Button
              size="sm"
              variant="primary"
              loading={scanning}
              onClick={() => void handleScan()}
            >
              <IconSearch size={12} /> 识别历史邮件
            </Button>
          </div>

          {items.length === 0 ? (
            <div className="text-center py-10 text-sm text-gh-text-secondary">
              {scanning ? "识别中..." : "点击「识别历史邮件」开始（不会自动创建平台，需逐项确认）"}
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div
                  key={item.platform}
                  className="rounded-lg border border-gh-border bg-gh-canvas-subtle px-3 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gh-text">{item.platform}</span>
                    <Badge color="#d29922">
                      {item.message_count} 封邮件 · {item.sender_count} 个发件人
                    </Badge>
                    <Badge color="#6e7681">
                      来源：{item.source === "domain" ? "域名启发式" : item.source}
                    </Badge>
                    <div className="flex-1" />
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={accepting === item.platform}
                      onClick={() => void handleAccept(item)}
                    >
                      <IconZap size={12} /> 纳入平台
                    </Button>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {item.senders.slice(0, 6).map((sender) => (
                      <span
                        key={sender}
                        className="rounded bg-gh-canvas-inset border border-gh-border px-1.5 py-0.5 text-[11px] font-mono text-gh-text-muted"
                      >
                        {sender}
                      </span>
                    ))}
                    {item.senders.length > 6 && (
                      <span className="text-[11px] text-gh-text-secondary">
                        +{item.senders.length - 6} 更多
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};
