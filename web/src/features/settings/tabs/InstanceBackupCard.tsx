import type React from "react";
import type { ChangeEvent } from "react";
import { useRef, useState } from "react";
import { api } from "../../../api/client";
import {
  IconAlertTriangle,
  IconArchive,
  IconDatabase,
  IconDownload,
  IconUpload,
} from "../../../components/icons";
import { ConfirmModal } from "../../../components/ui/ConfirmModal";
import { Button, Card } from "../../../components/ui/Primitives";
import { useApp } from "../../../store/AppContext";
import { SectionHeader } from "../SettingsControls";
import type { Toast } from "../types";

interface InstanceBackupCardProps {
  toast: Toast;
}

export const InstanceBackupCard: React.FC<InstanceBackupCardProps> = ({ toast }) => {
  const { logout } = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const handleExport = async (): Promise<void> => {
    setIsExporting(true);
    try {
      const archive: Blob = await api.exportInstanceBackup();
      const url: string = URL.createObjectURL(archive);
      const link: HTMLAnchorElement = document.createElement("a");
      link.href = url;
      link.download = `hx-email-instance-${new Date().toISOString().slice(0, 10)}.zip`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      toast("实例备份已下载", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "实例备份导出失败", "error");
    } finally {
      setIsExporting(false);
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file: File | undefined = event.target.files?.[0];
    event.target.value = "";
    if (file) setSelectedFile(file);
  };

  const handleImport = async (): Promise<void> => {
    if (!selectedFile) return;
    setIsImporting(true);
    try {
      const result = await api.importInstanceBackup(selectedFile);
      if (!result.restored) throw new Error("实例备份未恢复");
      toast("实例已恢复，请使用备份中的管理员重新登录", "success");
      await logout();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "实例备份导入失败", "error");
      setIsImporting(false);
    }
  };

  return (
    <>
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-gh-accent/10 text-gh-accent">
            <IconDatabase size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <SectionHeader>实例备份</SectionHeader>
            <p className="-mt-2 text-xs leading-5 text-gh-text-secondary">
              包含用户、设置、邮箱凭据、消息记录和静态文件，可在另一套 HX-Email 部署中恢复。
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Button
            variant="secondary"
            onClick={() => void handleExport()}
            loading={isExporting}
            disabled={isImporting}
            className="min-h-10"
          >
            <IconDownload size={15} />
            导出完整实例
          </Button>
          <Button
            variant="primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={isExporting || isImporting}
            className="min-h-10"
          >
            <IconUpload size={15} />
            选择备份 ZIP
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,application/zip"
            onChange={handleFileChange}
            className="sr-only"
            aria-label="选择实例备份 ZIP"
          />
        </div>

        {selectedFile && (
          <div className="mt-3 flex min-w-0 items-center gap-2 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2 text-xs text-gh-text-secondary">
            <IconArchive size={14} className="shrink-0 text-gh-accent" />
            <span className="truncate">{selectedFile.name}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedFile(null)}
              disabled={isImporting}
              className="ml-auto shrink-0"
            >
              移除
            </Button>
          </div>
        )}

        <div className="mt-4 flex gap-2 border-t border-gh-border pt-3 text-xs leading-5 text-gh-text-secondary">
          <IconAlertTriangle size={14} className="mt-0.5 shrink-0 text-gh-warning" />
          <span>导入会替换当前实例并使现有登录失效。备份包含敏感凭据，请妥善保管 ZIP 文件。</span>
        </div>
      </Card>

      <ConfirmModal
        open={selectedFile !== null}
        title="恢复实例备份"
        message={`将用 ${selectedFile?.name ?? "此文件"} 替换当前实例数据。恢复成功后需要使用备份中的管理员账号重新登录。`}
        confirmLabel="恢复并重新登录"
        loading={isImporting}
        onConfirm={() => void handleImport()}
        onCancel={() => {
          if (!isImporting) setSelectedFile(null);
        }}
      />
    </>
  );
};
