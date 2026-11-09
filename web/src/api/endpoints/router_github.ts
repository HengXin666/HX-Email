import type {
  GithubAttachResult,
  GithubManifestStart,
  GithubUserCheckResult,
  GithubVerifyResult,
  RouterActionSpec,
} from "../../types/messaging";
import { request } from "../core";

interface CapabilitiesPage {
  platforms: { platform: string; actions: RouterActionSpec[] }[];
}

/**
 * 出站动作开关的动作列表直接取能力声明, 前端不另写一份
 * 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
 */
function githubActions(platform = "github"): Promise<RouterActionSpec[]> {
  return request<CapabilitiesPage>(`/router/capabilities?platform=${platform}`).then(
    (page: CapabilitiesPage) => page.platforms[0]?.actions ?? [],
  );
}

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

  githubActions,

  // GitHub 用户账号 (gh CLI): 只提交 CLI 路径与仓库, 没有任何 token 字段
  githubUserSave: (data: {
    cli: string;
    repository: string;
    instance_id?: number;
  }): Promise<GithubUserCheckResult> =>
    request<GithubUserCheckResult>("/router/github_user/save", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  githubUserCheck: (instanceId: number): Promise<GithubUserCheckResult> =>
    request<GithubUserCheckResult>("/router/github_user/check", {
      method: "POST",
      body: JSON.stringify({ instance_id: instanceId }),
    }),

  githubAttach: (installationId: number, instanceId: number): Promise<GithubAttachResult> =>
    request<GithubAttachResult>(`/router/github/installations/${installationId}/attach`, {
      method: "POST",
      body: JSON.stringify({ instance_id: instanceId }),
    }),
};
