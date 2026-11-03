import type {
  GithubAttachResult,
  GithubManifestStart,
  GithubVerifyResult,
} from "../../types/messaging";
import { request } from "../core";

export const routerGithubApi = {
  // The server decides the public root: a browser opened on localhost says nothing about
  // whether GitHub can reach it, so the address is not ours to infer here.
  githubManifestStart: (): Promise<GithubManifestStart> =>
    request<GithubManifestStart>("/router/github/manifest"),

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
