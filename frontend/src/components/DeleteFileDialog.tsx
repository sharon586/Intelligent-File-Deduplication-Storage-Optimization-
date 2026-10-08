import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { filesApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { DeletePreview } from "../api/types";
import { formatBytes } from "../utils/format";

interface Props {
  fileId: number | null;
  onClose: () => void;
  onDeleted: (freedBytes: number, filename: string) => void;
}

/** Two-step safe delete: shows the storage impact first, then requires explicit confirmation. */
export default function DeleteFileDialog({ fileId, onClose, onDeleted }: Props) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fileId === null) return;
    let cancelled = false;
    setPreview(null);
    setConfirmed(false);
    setError(null);
    setLoading(true);
    filesApi
      .deletePreview(fileId)
      .then((p) => {
        if (!cancelled) setPreview(p);
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

  const handleDelete = async () => {
    if (!preview) return;
    setDeleting(true);
    setError(null);
    try {
      const result = await filesApi.remove(preview.file_id, "Manual delete from UI");
      onDeleted(result.storage_freed, preview.filename);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Dialog open={fileId !== null} onClose={deleting ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>Delete file</DialogTitle>
      <DialogContent dividers>
        {loading && (
          <Box sx={{ display: "grid", placeItems: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        )}
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {preview && (
          <Box sx={{ display: "grid", gap: 1.5 }}>
            <Typography>
              You are about to delete <strong>{preview.filename}</strong>.
            </Typography>
            <Typography variant="body2">
              Storage impact: <strong>{formatBytes(preview.storage_freed)}</strong> will be freed.
            </Typography>
            <Alert severity={preview.is_protected ? "error" : preview.is_last_copy ? "warning" : "info"}>
              {preview.message}
            </Alert>
            {preview.can_delete && (
              <FormControlLabel
                control={<Checkbox checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />}
                label="I understand this deletion is permanent and will be recorded in the history."
              />
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={deleting}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={!preview || !preview.can_delete || !confirmed || deleting}
          onClick={handleDelete}
        >
          {deleting ? "Deleting…" : "Delete"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
