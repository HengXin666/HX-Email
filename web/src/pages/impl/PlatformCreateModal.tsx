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
  onCreate: (name: string) => Promise<void>;
}

export const PlatformCreateModal: React.FC<PlatformCreateModalProps> = ({
  open,
  existingPlatforms,
  onClose,
  onCreate,
}) => {
  const { toast } = useToast();
  const [platformName, setPlatformName] = useState("");
  const [selectedPresetKey, setSelectedPresetKey] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const trimmedName = platformName.trim();

  const existingNames = useMemo(
    () => new Set(existingPlatforms.map((platform: Platform) => platform.name)),
    [existingPlatforms],
  );
  const isDuplicate = trimmedName.length > 0 && existingNames.has(trimmedName);
  const canCreate = trimmedName.length > 0 && !isDuplicate && !isSaving;

  useEffect(() => {
    if (!open) {
      setPlatformName("");
      setSelectedPresetKey(null);
      setIsSaving(false);
    }
  }, [open]);

  const handlePresetSelect = (preset: (typeof PRESET_PLATFORMS)[number]): void => {
    if (existingNames.has(preset.name)) return;
    setSelectedPresetKey(preset.key);
    setPlatformName(preset.name);
  };

  const handleNameChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setPlatformName(event.target.value);
    setSelectedPresetKey(null);
  };

  const handleCreate = async (): Promise<void> => {
    if (!canCreate) return;

    setIsSaving(true);
    try {
      await onCreate(trimmedName);
      toast("平台已创建", "success");
      setPlatformName("");
      setSelectedPresetKey(null);
      onClose();
    } catch (error: unknown) {
      toast(getErrorMessage(error), "error");
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
          <Button variant="primary" onClick={handleCreate} disabled={!canCreate} loading={isSaving}>
            创建
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <div className="text-xs font-medium text-gh-text-muted mb-2">预选平台</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {PRESET_PLATFORMS.map((preset) => {
              const isSelected = selectedPresetKey === preset.key;
              const isAdded = existingNames.has(preset.name);

              return (
                <button
                  key={preset.key}
                  type="button"
                  aria-pressed={isSelected}
                  disabled={isAdded}
                  onClick={() => handlePresetSelect(preset)}
                  className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all ${
                    isSelected
                      ? "border-gh-accent bg-gh-accent/10"
                      : "border-gh-border bg-gh-canvas-inset hover:border-gh-text-muted hover:bg-gh-border/20"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
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
            label="平台名称"
            value={platformName}
            onChange={handleNameChange}
            placeholder="例如：OpenAI"
            autoFocus
          />
          {isDuplicate && <div className="mt-1.5 text-xs text-gh-danger">同名平台已存在</div>}
        </div>
      </div>
    </Modal>
  );
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "平台创建失败";
}
