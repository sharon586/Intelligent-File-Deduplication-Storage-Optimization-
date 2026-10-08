import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Pagination,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import LockIcon from "@mui/icons-material/Lock";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useCallback, useEffect, useState } from "react";
import { duplicatesApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { DuplicateGroup, FileBrief, Page } from "../api/types";
import DeleteFileDialog from "../components/DeleteFileDialog";
import { formatBytes, formatDate, shortHash } from "../utils/format";

function FileRow({ file, original, onDelete }: { file: FileBrief; original: boolean; onDelete: (id: number) => void }) {
  return (
    <TableRow>
      <TableCell>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {file.is_protected && <LockIcon fontSize="inherit" color="warning" />}
          {file.original_filename}
        </Box>
      </TableCell>
      <TableCell>{original ? <Chip size="small" color="primary" label="Original" /> : <Chip size="small" color="warning" label="Duplicate" />}</TableCell>
      <TableCell align="right">{formatBytes(file.size_bytes)}</TableCell>
      <TableCell>{formatDate(file.uploaded_at)}</TableCell>
      <TableCell align="right">
        <Tooltip title="Delete this file">
          <IconButton size="small" color="error" onClick={() => onDelete(file.id)}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

export default function Duplicates() {
  const [data, setData] = useState<Page<DuplicateGroup> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("savings");
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [cleanupGroup, setCleanupGroup] = useState<DuplicateGroup | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await duplicatesApi.groups(page, 10, sortBy);
      setData(result);
      setError(null);
      if (result.items.length === 0 && result.total > 0 && page > 1) setPage(Math.max(1, result.pages));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [page, sortBy]);

  useEffect(() => {
    void load();
  }, [load]);

  const runCleanup = async () => {
    if (!cleanupGroup) return;
    setCleaning(true);
    try {
      const r = await duplicatesApi.cleanup(cleanupGroup.id);
      const skipped = r.skipped_protected.length ? ` ${r.skipped_protected.length} protected file(s) were kept.` : "";
      setNotice({ type: "success", text: `Deleted ${r.deleted_count} duplicate(s), freed ${formatBytes(r.storage_freed)}.${skipped}` });
      setCleanupGroup(null);
      void load();
    } catch (e) {
      setNotice({ type: "error", text: getErrorMessage(e) });
    } finally {
      setCleaning(false);
    }
  };

  const rescan = async () => {
    try {
      const r = await duplicatesApi.rescan();
      setNotice({ type: r.queued ? "info" : "error", text: r.message });
      if (r.queued) window.setTimeout(() => void load(), 2000);
    } catch (e) {
      setNotice({ type: "error", text: getErrorMessage(e) });
    }
  };

  const cleanableSavings = cleanupGroup ? cleanupGroup.duplicates.filter((d) => !d.is_protected).reduce((s, d) => s + d.size_bytes, 0) : 0;
  const cleanableCount = cleanupGroup ? cleanupGroup.duplicates.filter((d) => !d.is_protected).length : 0;

  return (
    <Box sx={{ display: "grid", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Duplicate groups
        </Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
          <TextField size="small" select label="Sort by" value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPage(1); }} sx={{ minWidth: 170 }}>
            <MenuItem value="savings">Potential savings</MenuItem>
            <MenuItem value="size">File size</MenuItem>
            <MenuItem value="count">Number of copies</MenuItem>
            <MenuItem value="created">Newest</MenuItem>
          </TextField>
          <Button startIcon={<RefreshIcon />} onClick={() => void rescan()}>
            Rescan
          </Button>
        </Box>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {loading && !data && (
        <Box sx={{ display: "grid", placeItems: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}
      {data && data.items.length === 0 && !loading && (
        <Alert severity="success">No duplicate files found. Files with identical content will appear here as groups.</Alert>
      )}

      {data?.items.map((g) => (
        <Accordion key={g.id} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", width: "100%", pr: 1 }}>
              <Typography sx={{ fontWeight: 600, flexGrow: 1, minWidth: 180 }}>
                {g.original?.original_filename ?? "Unknown file"}
              </Typography>
              <Chip size="small" label={`${g.file_count} copies`} />
              <Chip size="small" variant="outlined" label={`Each ${formatBytes(g.file_size)}`} />
              <Chip size="small" color="success" label={`Save ${formatBytes(g.potential_savings)}`} />
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
              SHA-256 {shortHash(g.sha256)} · Storage consumed {formatBytes(g.storage_consumed)} · Potential savings {formatBytes(g.potential_savings)}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Filename</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell>Uploaded</TableCell>
                  <TableCell align="right">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {g.original && <FileRow file={g.original} original onDelete={setDeleteId} />}
                {g.duplicates.map((d) => (
                  <FileRow key={d.id} file={d} original={false} onDelete={setDeleteId} />
                ))}
              </TableBody>
            </Table>
            <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
              <Button color="error" variant="outlined" startIcon={<DeleteIcon />} onClick={() => setCleanupGroup(g)}>
                Delete all duplicates (keep original)
              </Button>
            </Box>
          </AccordionDetails>
        </Accordion>
      ))}

      {data && data.pages > 1 && (
        <Box sx={{ display: "flex", justifyContent: "center" }}>
          <Pagination count={data.pages} page={page} onChange={(_, p) => setPage(p)} color="primary" />
        </Box>
      )}

      <DeleteFileDialog
        fileId={deleteId}
        onClose={() => setDeleteId(null)}
        onDeleted={(freed, name) => {
          setDeleteId(null);
          setNotice({ type: "success", text: `Deleted ${name}. Freed ${formatBytes(freed)}.` });
          void load();
        }}
      />

      <Dialog open={cleanupGroup !== null} onClose={cleaning ? undefined : () => setCleanupGroup(null)} fullWidth maxWidth="sm">
        <DialogTitle>Delete all duplicates</DialogTitle>
        <DialogContent dividers>
          {cleanupGroup && (
            <Box sx={{ display: "grid", gap: 1.5 }}>
              <Typography>
                The original <strong>{cleanupGroup.original?.original_filename}</strong> will be kept.
              </Typography>
              <Typography>
                <strong>{cleanableCount}</strong> duplicate file(s) will be deleted, freeing <strong>{formatBytes(cleanableSavings)}</strong>.
              </Typography>
              {cleanableCount < cleanupGroup.duplicates.length && (
                <Alert severity="info">Protected files are never deleted and will be skipped.</Alert>
              )}
              <Alert severity="warning">This cannot be undone. Every deletion is recorded in the history.</Alert>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCleanupGroup(null)} disabled={cleaning}>
            Cancel
          </Button>
          <Button color="error" variant="contained" onClick={() => void runCleanup()} disabled={cleaning || cleanableCount === 0}>
            {cleaning ? "Deleting…" : "Confirm delete"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={notice !== null} autoHideDuration={6000} onClose={() => setNotice(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        {notice ? (
          <Alert severity={notice.type} onClose={() => setNotice(null)} variant="filled">
            {notice.text}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
}
