export interface User {
  id: number;
  username: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type FileStatus = "pending" | "processing" | "ready" | "failed";

export interface FileItem {
  id: number;
  original_filename: string;
  extension: string;
  content_type: string;
  category: string;
  size_bytes: number;
  status: FileStatus;
  is_protected: boolean;
  is_duplicate: boolean;
  duplicate_group_id: number | null;
  sha256: string | null;
  uploaded_at: string;
  processed_at: string | null;
}

export interface FileDetail extends FileItem {
  error_message: string | null;
  file_metadata: { detected_mime: string | null; extension: string; extra: Record<string, unknown> | null } | null;
  group: {
    id: number;
    file_count: number;
    file_size: number;
    potential_savings: number;
    original_file_id: number | null;
    original_filename: string | null;
  } | null;
}

export interface FileBrief {
  id: number;
  original_filename: string;
  size_bytes: number;
  uploaded_at: string;
  is_protected: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface DeletePreview {
  file_id: number;
  filename: string;
  size_bytes: number;
  is_protected: boolean;
  is_duplicate: boolean;
  group_id: number | null;
  copies_remaining: number;
  is_last_copy: boolean;
  storage_freed: number;
  can_delete: boolean;
  message: string;
}

export interface DeleteResponse {
  deleted_count: number;
  storage_freed: number;
  skipped_protected: number[];
}

export interface DuplicateGroup {
  id: number;
  sha256: string;
  file_size: number;
  file_count: number;
  storage_consumed: number;
  potential_savings: number;
  created_at: string;
  original: FileBrief | null;
  duplicates: FileBrief[];
}

export interface AnalyticsSummary {
  total_files: number;
  total_storage: number;
  duplicate_files: number;
  duplicate_storage: number;
  duplicate_groups: number;
  potential_savings: number;
  savings_percent: number;
  pending_files: number;
  largest_files: FileBrief[];
  recent_uploads: FileBrief[];
  by_category: { category: string; count: number; size_bytes: number }[];
  uploads_by_day: { date: string; count: number }[];
}

export interface DeletionRecord {
  id: number;
  file_id: number | null;
  filename: string;
  sha256: string | null;
  size_bytes: number;
  storage_freed: number;
  was_duplicate: boolean;
  group_id: number | null;
  reason: string | null;
  deleted_at: string;
}

export interface AuditRecord {
  id: number;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface FileFilters {
  q?: string;
  file_type?: string;
  min_size?: number;
  max_size?: number;
  duplicate_status?: "any" | "duplicate" | "original" | "unique";
  date_from?: string;
  date_to?: string;
  sort_by?: "uploaded_at" | "name" | "size" | "type";
  sort_order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
