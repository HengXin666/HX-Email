import { request } from "../core";

export interface GoogleVerificationFileInfo {
  filename: string;
  url: string;
}

export interface GoogleVerificationFileList {
  files: GoogleVerificationFileInfo[];
}

export const googleVerificationApi = {
  listGoogleVerificationFiles: () =>
    request<GoogleVerificationFileList>("/admin/google-verification"),

  uploadGoogleVerificationFile: (file: File) => {
    const filename = encodeURIComponent(file.name);
    return request<GoogleVerificationFileInfo>(`/admin/google-verification?filename=${filename}`, {
      method: "POST",
      headers: { "Content-Type": "text/html" },
      body: file,
    });
  },

  deleteGoogleVerificationFile: (filename: string) =>
    request<null>(`/admin/google-verification/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),
};
