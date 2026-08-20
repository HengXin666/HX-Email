import React, { useEffect, useMemo, useState } from "react";
import { Badge, Button, Input, Modal } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { Platform } from "../../types";
import { PlatformLogo } from "./PlatformLogo";
import { PRESET_PLATFORMS } from "./platform_catalog";

interface PlatformCreateModalProps {
  open: boolean;
  existingPlatforms: Platform[];
  onClose: () => void;
  onCreate: (names: string[]) => Promise<void>;
}

export const PlatformCreateModal: React.FC<PlatformCreateModalProps> = ({
  open,
  existingPlatforms,
  onClose,
  onCreate,
}) => {
  const { toast } = useToast();
  const [platformName, setPlatformName] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [isSaving, setIsSaving] = useState(false);
  const trimmedName = platformName.trim();

  const existingNames = useMemo(
    () => new Set(existingPlatforms.map((platform: Platform) => platform.name)),
    [existingPlatforms],
  );
  const isDuplicate = trimmedName.length > 0 && existingNames.has(trimmedName);
  const selectedPresets = PRESET_PLATFORMS.filter((preset) => selectedKeys.has(preset.key));
  const customNames = trimmedName && !isDuplicate ? [trimmedName] : [];
  const createNames = [...new Set([...selectedPresets.map((p) => p.name), ...customNames])];
  const canCreate = createNames.length > 0 && !isSaving;

  useEffect(() => {
    if (!open) {
      setPlatformName("");
      setSelectedKeys(new Set());
      setIsSaving(false);
    }
  }, [open]);

  const togglePreset = (preset: (typeof PRESET_PLATFORMS)[number]): void => {
    if (existingNames.has(preset.name)) return;
    setSelectedKeys((previous) => {
      const next = new Set(previous);
      if (next.has(preset.key)) {
        next.delete(preset.key);
      } else {
        next.add(preset.key);
      }
      return next;
    });
  };

  const handleCreate = async (): Promise<void> => {
    if (!canCreate) return;

    setIsSaving(true);
    try {
      await onCreate(createNames);
      toast(`已创建 ${createNames.length} 个平台`, "success");
      setPlatformName("");
      setSelectedKeys(new Set());
      onClose();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "平台创建失败", "error");
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = (): void => {
    if (isSaving) return;
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="新建平台"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isSaving}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={() => void handleCreate()}
            disabled={!canCreate}
            loading={isSaving}
          >
            创建{createNames.length > 1 ? ` (${createNames.length})` : ""}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <div className="text-xs font-medium text-gh-text-muted mb-2">
            预选平台（可多选）
            {selectedPresets.length > 0 && (
              <span className="ml-1.5 text-gh-accent">已选 {selectedPresets.length} 个</span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {PRESET_PLATFORMS.map((preset) => {
              const isSelected = selectedKeys.has(preset.key);
              const isAdded = existingNames.has(preset.name);

              return (
                <button
                  key={preset.key}
                  type="button"
                  aria-pressed={isSelected}
                  disabled={isAdded}
                  onClick={() => togglePreset(preset)}
                  className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all ${
                    isSelected
                      ? "border-gh-accent bg-gh-accent/10"
                      : "border-gh-border bg-gh-canvas-inset hover:border-gh-text-muted hover:bg-gh-border/20"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                      isSelected ? "border-gh-accent bg-gh-accent" : "border-gh-text-muted"
                    }`}
                  >
                    {isSelected && (
                      <svg viewBox="0 0 12 12" className="h-2.5 w-2.5 text-white" fill="none">
                        <path
                          d="M2 6.5 4.8 9 10 3.5"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </span>
                  <PlatformLogo name={preset.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gh-text truncate">{preset.name}</div>
                    <div className="text-xs text-gh-text-secondary truncate">
                      {preset.description}
                    </div>
                  </div>
                  {isAdded && <Badge color="#3fb950">已添加</Badge>}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <Input
            label="自定义平台名称"
            value={platformName}
            onChange={(event) => setPlatformName(event.target.value)}
            placeholder="例如：OpenAI（可与上方多选同时创建）"
            autoFocus
          />
          {isDuplicate && <div className="mt-1.5 text-xs text-gh-danger">同名平台已存在</div>}
        </div>
      </div>
    </Modal>
  );
};
