import { Download, Search, Upload } from "lucide-react";

import type { UsableEmail } from "../types";
import { Button } from "./ui/button";

type ToolbarProps = {
  query: string;
  onQuery: (query: string) => void;
};

type EmailTableProps = {
  emails: UsableEmail[];
  kindLabels: Record<UsableEmail["kind"], string>;
  statusLabels: Record<UsableEmail["status"], string>;
  onDeactivate: (email: UsableEmail) => void;
};

type InfoPanelProps = {
  actions?: boolean;
  rows: string[];
  title: string;
};

export function Toolbar({ query, onQuery }: ToolbarProps) {
  return (
    <div className="toolbar">
      <label className="search-field">
        <Search size={16} />
        <input
          aria-label="关键词"
          onChange={(event) => onQuery(event.target.value)}
          placeholder="地址或标签"
          type="search"
          value={query}
        />
      </label>
      <select aria-label="类型">
        <option>全部类型</option>
        <option>主邮箱地址</option>
        <option>别名邮箱地址</option>
        <option>临时邮箱地址</option>
      </select>
      <select aria-label="状态">
        <option>全部状态</option>
        <option>可用</option>
        <option>已停用</option>
      </select>
      <select aria-label="平台绑定">
        <option>全部绑定</option>
        <option>未绑定平台</option>
        <option>已绑定平台</option>
      </select>
    </div>
  );
}

export function EmailTable({
  emails,
  kindLabels,
  onDeactivate,
  statusLabels,
}: EmailTableProps) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>地址</th>
            <th>类型</th>
            <th>标签</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {emails.map((email) => (
            <tr key={email.id}>
              <td>{email.address}</td>
              <td>{kindLabels[email.kind]}</td>
              <td>{email.label || "未标记"}</td>
              <td>{statusLabels[email.status]}</td>
              <td>
                <Button
                  disabled={email.status !== "active"}
                  onClick={() => onDeactivate(email)}
                  type="button"
                >
                  停用
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InfoPanel({ actions = false, rows, title }: InfoPanelProps) {
  return (
    <article className="info-panel">
      <h2>{title}</h2>
      <div className="info-rows">
        {(rows.length ? rows : ["暂无数据"]).map((row) => (
          <span key={row}>{row}</span>
        ))}
      </div>
      {actions ? (
        <div className="inline-actions">
          <Button type="button">
            <Upload size={16} />
            导入
          </Button>
          <Button type="button">
            <Download size={16} />
            导出
          </Button>
        </div>
      ) : null}
    </article>
  );
}
