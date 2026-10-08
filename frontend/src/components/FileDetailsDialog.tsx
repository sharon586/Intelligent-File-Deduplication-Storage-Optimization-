import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { filesApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { FileDetail } from "../api/types";
import { formatBytes, formatDate } from "../utils/format";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 1, py: 0.5 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function FileDetailsDialog({ fileId, onClose }: { fileId: number | null; onClose: () => void }) {
  const [detail, setDetail] = useState<FileDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (fileId === null) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    setLoading(true);
    filesApi
      .get(fileId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(getErrorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  return (
    <Dialog open={fileId !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>File details</DialogTitle>
      <DialogContent dividers>
        {loading && (
          <Box sx={{ display: "grid", placeItems: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {detail && (
          <>
            <Row label="Filename" value={detail.original_filename} />
            <Row label="Size" value={`${formatBytes(detail.size_bytes)} (${detail.size_bytes.toLocaleString()} bytes)`} />
            <Row label="Type" value={`${detail.category} (${detail.content_type})`} />
            <Row label="Extension" value={detail.extension || "-"} />
            <Row label="Status" value={detail.status} />
            <Row label="Uploaded" value={formatDate(detail.uploaded_at)} />
            <Row label="Processed" value={formatDate(detail.processed_at)} />
            <Row label="SHA-256" value={detail.sha256 ?? "Not calculated yet"} />
            <Row label="Protected" value={detail.is_protected ? "Yes" : "No"} />
            {detail.file_metadata && <Row label="Detected MIME" value={detail.file_metadata.detected_mime ?? "-"} />}
            {detail.error_message && <Alert severity="error" sx={{ mt: 1 }}>{detail.error_message}</Alert>}
            {detail.group ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                {detail.is_duplicate ? "Duplicate of" : "Original of a group with"}{" "}
                {detail.is_duplicate ? <strong>{detail.group.original_filename}</strong> : <strong>{detail.group.file_count - 1} copies</strong>}
                . Group of {detail.group.file_count} files; potential savings {formatBytes(detail.group.potential_savings)}.
              </Alert>
            ) : (
              detail.status === "ready" && <Alert severity="success" sx={{ mt: 2 }}>No duplicates found for this file.</Alert>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
