import { api } from "./client";
import type {
  AnalyticsSummary,
  AuditRecord,
  DeletePreview,
  DeleteResponse,
  DeletionRecord,
  DuplicateGroup,
  FileDetail,
  FileFilters,
  FileItem,
  Page,
  TokenResponse,
  User,
} from "./types";

export const authApi = {
  async login(username: string, password: string): Promise<TokenResponse> {
    const body = new URLSearchParams({ username, password });
    const { data } = await api.post<TokenResponse>("/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },
  async register(username: string, email: string, password: string): Promise<User> {
    const { data } = await api.post<User>("/auth/register", { username, email, password });
    return data;
  },
  async me(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },
};

export const filesApi = {
  async list(filters: FileFilters): Promise<Page<FileItem>> {
    const params: Record<string, string | number> = {};
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "" && value !== "any") params[key] = value as string | number;
    });
    const { data } = await api.get<Page<FileItem>>("/files", { params });
    return data;
  },
  async get(id: number): Promise<FileDetail> {
    const { data } = await api.get<FileDetail>(`/files/${id}`);
    return data;
  },
  async upload(file: File, onProgress?: (percent: number) => void): Promise<FileItem> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<FileItem>("/files/upload", form, {
      timeout: 0,
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
    return data;
  },
  async download(file: { id: number; original_filename: string }): Promise<void> {
    const response = await api.get<Blob>(`/files/${file.id}/download`, { responseType: "blob", timeout: 0 });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.original_filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  async deletePreview(id: number): Promise<DeletePreview> {
    const { data } = await api.get<DeletePreview>(`/files/${id}/delete-preview`);
    return data;
  },
  async remove(id: number, reason?: string): Promise<DeleteResponse> {
    const { data } = await api.delete<DeleteResponse>(`/files/${id}`, { params: { confirm: true, reason } });
    return data;
  },
  async setProtected(id: number, isProtected: boolean): Promise<FileItem> {
    const { data } = await api.patch<FileItem>(`/files/${id}/protect`, { is_protected: isProtected });
    return data;
  },
  async reprocess(id: number): Promise<FileItem> {
    const { data } = await api.post<FileItem>(`/files/${id}/reprocess`);
    return data;
  },
};

export const duplicatesApi = {
  async groups(page: number, pageSize: number, sortBy: string): Promise<Page<DuplicateGroup>> {
    const { data } = await api.get<Page<DuplicateGroup>>("/duplicates/groups", {
      params: { page, page_size: pageSize, sort_by: sortBy, sort_order: "desc" },
    });
    return data;
  },
  async cleanup(groupId: number): Promise<DeleteResponse> {
    const { data } = await api.post<DeleteResponse>(`/duplicates/groups/${groupId}/cleanup`, { confirm: true });
    return data;
  },
  async rescan(): Promise<{ message: string; queued: boolean }> {
    const { data } = await api.post<{ message: string; queued: boolean }>("/duplicates/rescan");
    return data;
  },
};

export const analyticsApi = {
  async summary(): Promise<AnalyticsSummary> {
    const { data } = await api.get<AnalyticsSummary>("/analytics/summary");
    return data;
  },
  async deletions(page: number, pageSize: number): Promise<Page<DeletionRecord>> {
    const { data } = await api.get<Page<DeletionRecord>>("/history/deletions", {
      params: { page, page_size: pageSize },
    });
    return data;
  },
  async audit(page: number, pageSize: number): Promise<Page<AuditRecord>> {
    const { data } = await api.get<Page<AuditRecord>>("/history/audit", { params: { page, page_size: pageSize } });
    return data;
  },
};
