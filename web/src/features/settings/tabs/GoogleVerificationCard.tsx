import type React from "react";
import type { ChangeEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/client";
import { IconGlobe, IconTrash, IconUpload } from "../../../components/icons";
import { ConfirmModal } from "../../../components/ui/ConfirmModal";
import { Button, Card } from "../../../components/ui/Primitives";
import { SectionHeader } from "../SettingsControls";
import type { Toast } from "../types";

interface GoogleVerificationFile {
  filename: string;
  url: string;
}

interface GoogleVerificationCardProps {
  toast: Toast;
}

export const GoogleVerificationCard: React.FC<GoogleVerificationCardProps> = ({ toast }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<GoogleVerificationFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<GoogleVerificationFile | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const loadFiles = async (): Promise<void> => {
    try {
      const result = await api.listGoogleVerificationFiles();
      setFiles(result.files);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "获取验证文件失败", "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file: File | undefined = event.target.files?.[0];
    event.target.value = "";
    if (file) setSelectedFile(file);
  };

  const handleUpload = async (): Promise<void> => {
    if (!selectedFile) return;
    setIsUploading(true);
    try {
      const result = await api.uploadGoogleVerificationFile(selectedFile);
      setSelectedFile(null);
      await loadFiles();
      toast(`验证文件已上传：${window.location.origin}${result.url}`, "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "上传失败", "error");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (!pendingDelete) return;
    setIsDeleting(true);
    try {
      await api.deleteGoogleVerificationFile(pendingDelete.filename);
      setPendingDelete(null);
      await loadFiles();
      toast("验证文件已删除", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "删除失败", "error");
    } finally {
      setIsDeleting(false);
    }
  };

  const current: GoogleVerificationFile | undefined = files[0];

  return (
    <>
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-gh-accent/10 text-gh-accent">
            <IconGlobe size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <SectionHeader>Google 站点验证</SectionHeader>
            <p className="-mt-2 text-xs leading-5 text-gh-text-secondary">
              在 Google Search Console 选择「HTML 文件」方式验证站点所有权，下载生成的
              google&lt;hash&gt;.html 文件后在此上传；系统会在站点根路径公开提供该文件，供 Google
              完成验证。
            </p>
          </div>
        </div>

        {isLoading ? (
          <div className="mt-4 text-sm text-gh-text-secondary">加载中...</div>
        ) : current ? (
          <div className="mt-4 space-y-2">
            <div className="flex min-w-0 items-center gap-2 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-gh-text">{current.filename}</div>
                <a
                  href={current.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-gh-accent hover:underline"
                >
                  {window.location.origin}
                  {current.url}
                </a>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPendingDelete(current)}
                className="shrink-0"
              >
                <IconTrash size={14} /> 删除
              </Button>
            </div>
            <p className="text-xs leading-5 text-gh-text-secondary">
              验证地址需公开可访问。上传新的验证文件会替换当前文件。
            </p>
          </div>
        ) : (
          <div className="mt-4 rounded-md border border-dashed border-gh-border bg-gh-canvas-inset px-4 py-6 text-center text-xs text-gh-text-secondary">
            尚未上传验证文件
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-gh-border pt-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            <IconUpload size={13} /> 选择验证文件
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleUpload()}
            loading={isUploading}
            disabled={!selectedFile}
          >
            上传
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".html,text/html"
            onChange={handleFileChange}
            className="sr-only"
            aria-label="选择 Google 站点验证 HTML 文件"
          />
          {selectedFile && (
            <span className="flex min-w-0 items-center gap-1 text-xs text-gh-text-secondary">
              <span className="truncate">{selectedFile.name}</span>
              <button
                type="button"
                onClick={() => setSelectedFile(null)}
                className="text-gh-accent hover:underline"
              >
                移除
              </button>
            </span>
          )}
        </div>
      </Card>

      <ConfirmModal
        open={pendingDelete !== null}
        title="删除验证文件"
        message={`确定删除 ${pendingDelete?.filename ?? ""}？删除后 Google 将无法再通过该文件验证站点所有权。`}
        confirmLabel="确认删除"
        loading={isDeleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
};
