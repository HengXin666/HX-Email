import { request, requestBlob } from "../core";

export interface InstanceBackupImportResult {
  restored: boolean;
  requires_relogin: boolean;
}

export const backupApi = {
  exportInstanceBackup: () => requestBlob("/admin/backup/export"),

  importInstanceBackup: (archive: Blob) =>
    request<InstanceBackupImportResult>("/admin/backup/import", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: archive,
    }),
};
