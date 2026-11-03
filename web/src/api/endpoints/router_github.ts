import type {
  GithubAttachResult,
  GithubManifestStart,
  GithubVerifyResult,
} from "../../types/messaging";
import { request } from "../core";

export const routerGithubApi = {
  githubManifestStart: (baseUrl: string): Promise<GithubManifestStart> =>
    request<GithubManifestStart>(`/router/github/manifest?base_url=${encodeURIComponent(baseUrl)}`),

  githubVerify: (instanceId: number): Promise<GithubVerifyResult> =>
    request<GithubVerifyResult>("/router/github/verify", {
      method: "POST",
      body: JSON.stringify({ instance_id: instanceId }),
    }),

  githubAttach: (installationId: number, instanceId: number): Promise<GithubAttachResult> =>
    request<GithubAttachResult>(`/router/github/installations/${installationId}/attach`, {
      method: "POST",
      body: JSON.stringify({ instance_id: instanceId }),
    }),
};
