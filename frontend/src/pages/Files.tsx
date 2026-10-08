import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  LinearProgress,
  MenuItem,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import LockIcon from "@mui/icons-material/Lock";
import LockOpenIcon from "@mui/icons-material/LockOpen";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { filesApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { FileFilters, FileItem, Page } from "../api/types";
import DeleteFileDialog from "../components/DeleteFileDialog";
import FileDetailsDialog from "../components/FileDetailsDialog";
import { formatBytes, formatDate } from "../utils/format";

const CATEGORIES = ["image", "document", "video", "audio", "archive", "code", "other"];
const MB = 1024 * 1024;

interface UploadState {
  current: string;
  index: number;
  total: number;
  percent: number;
}

function statusChip(file: FileItem) {
  switch (file.status) {
    case "ready":
      return <Chip size="small" color="success" variant="outlined" label="Ready" />;
    case "failed":
      return <Chip size="small" color="error" label="Failed" />;
    default:
      return <Chip size="small" color="info" variant="outlined" label={file.status === "pending" ? "Queued" : "Analysing"} />;
  }
}

function duplicateChip(file: FileItem) {
  if (file.status !== "ready") return <Typography variant="caption" color="text.secondary">-</Typography>;
  if (file.is_duplicate) return <Chip size="small" color="warning" label="Duplicate" />;
  if (file.duplicate_group_id !== null) return <Chip size="small" color="primary" variant="outlined" label="Original" />;
  return <Chip size="small" variant="outlined" label="Unique" />;
}

export default function Files() {
  const [data, setData] = useState<Page<FileItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const [fileType, setFileType] = useState("");
  const [minMb, setMinMb] = useState("");
  const [maxMb, setMaxMb] = useState("");
  const [duplicateStatus, setDuplicateStatus] = useState<NonNullable<FileFilters["duplicate_status"]>>("any");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<NonNullable<FileFilters["sort_by"]>>("uploaded_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [search, setSearch] = useState("");

  const [upload, setUpload] = useState<UploadState | null>(null);
  const [detailsId, setDetailsId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Debounce the filename search box.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const buildFilters = useCallback((): FileFilters => {
    const min = minMb !== "" ? Math.max(0, Math.round(Number(minMb) * MB)) : undefined;
    const max = maxMb !== "" ? Math.max(0, Math.round(Number(maxMb) * MB)) : undefined;
    return {
      q: search || undefined,
      file_type: fileType || undefined,
      min_size: min !== undefined && !Number.isNaN(min) ? min : undefined,
      max_size: max !== undefined && !Number.isNaN(max) ? max : undefined,
      duplicate_status: duplicateStatus,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      page,
      page_size: pageSize,
    };
  }, [search, fileType, minMb, maxMb, duplicateStatus, dateFrom, dateTo, sortBy, sortOrder, page, pageSize]);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const result = await filesApi.list(buildFilters());
        setData(result);
        setError(null);
        // Landed on a page that no longer exists (e.g. after deleting the last item on it).
        if (result.items.length === 0 && result.total > 0 && page > 1) setPage(Math.max(1, result.pages));
      } catch (e) {
        setError(getErrorMessage(e));
      } finally {
        setLoading(false);
      }
    },
    [buildFilters, page],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while files are still being hashed by the background worker.
  const hasActive = data?.items.some((f) => f.status === "pending" || f.status === "processing") ?? false;
  useEffect(() => {
    if (!hasActive) return;
    const t = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(t);
  }, [hasActive, load]);

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  const clearFilters = () => {
    setSearchInput("");
    setSearch("");
    setFileType("");
    setMinMb("");
    setMaxMb("");
    setDuplicateStatus("any");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  };

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length === 0) return;

    let ok = 0;
    const failures: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUpload({ current: file.name, index: i + 1, total: files.length, percent: 0 });
      try {
        await filesApi.upload(file, (percent) => setUpload({ current: file.name, index: i + 1, total: files.length, percent }));
        ok += 1;
      } catch (err) {
        failures.push(`${file.name}: ${getErrorMessage(err)}`);
      }
    }
    setUpload(null);
    if (failures.length > 0) {
      setNotice({ type: "error", text: failures.slice(0, 3).join(" | ") + (failures.length > 3 ? ` (+${failures.length - 3} more)` : "") });
    } else {
      setNotice({ type: "success", text: `${ok} file(s) uploaded. Duplicate detection is running in the background.` });
    }
    setPage(1);
    void load(true);
  };

  const handleDownload = async (file: FileItem) => {
    try {
      await filesApi.download(file);
    } catch (err) {
      setNotice({ type: "error", text: getErrorMessage(err) });
    }
  };

  const toggleProtect = async (file: FileItem) => {
    try {
      await filesApi.setProtected(file.id, !file.is_protected);
      setNotice({ type: "success", text: file.is_protected ? "Protection removed" : "File is now protected from deletion" });
      void load(true);
    } catch (err) {
      setNotice({ type: "error", text: getErrorMessage(err) });
    }
  };

  const reprocess = async (file: FileItem) => {
    try {
      await filesApi.reprocess(file.id);
      setNotice({ type: "success", text: "File queued for analysis again" });
      void load(true);
    } catch (err) {
      setNotice({ type: "error", text: getErrorMessage(err) });
    }
  };

  return (
    <Box sx={{ display: "grid", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Files
        </Typography>
        <Box>
          <input ref={fileInput} type="file" multiple hidden onChange={handleUpload} />
          <Button variant="contained" startIcon={<CloudUploadIcon />} disabled={upload !== null} onClick={() => fileInput.current?.click()}>
            Upload files
          </Button>
        </Box>
      </Box>

      {upload && (
        <Card>
          <CardContent>
            <Typography variant="body2" gutterBottom>
              Uploading {upload.index} of {upload.total}: {upload.current} ({upload.percent}%)
            </Typography>
            <LinearProgress variant="determinate" value={upload.percent} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          <TextField size="small" label="Search filename" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
          <TextField size="small" select label="File type" value={fileType} onChange={(e) => resetPage(setFileType)(e.target.value)}>
            <MenuItem value="">All types</MenuItem>
            {CATEGORIES.map((c) => (
              <MenuItem key={c} value={c}>
                {c}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            select
            label="Duplicates"
            value={duplicateStatus}
            onChange={(e) => resetPage(setDuplicateStatus)(e.target.value as NonNullable<FileFilters["duplicate_status"]>)}
          >
            <MenuItem value="any">All files</MenuItem>
            <MenuItem value="duplicate">Redundant copies</MenuItem>
            <MenuItem value="original">Originals with copies</MenuItem>
            <MenuItem value="unique">Unique files</MenuItem>
          </TextField>
          <TextField size="small" type="number" label="Min size (MB)" value={minMb} onChange={(e) => resetPage(setMinMb)(e.target.value)} slotProps={{ htmlInput: { min: 0, step: "any" } }} />
          <TextField size="small" type="number" label="Max size (MB)" value={maxMb} onChange={(e) => resetPage(setMaxMb)(e.target.value)} slotProps={{ htmlInput: { min: 0, step: "any" } }} />
          <TextField size="small" type="date" label="Uploaded from" value={dateFrom} onChange={(e) => resetPage(setDateFrom)(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField size="small" type="date" label="Uploaded to" value={dateTo} onChange={(e) => resetPage(setDateTo)(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField size="small" select label="Sort by" value={sortBy} onChange={(e) => resetPage(setSortBy)(e.target.value as NonNullable<FileFilters["sort_by"]>)}>
            <MenuItem value="uploaded_at">Upload date</MenuItem>
            <MenuItem value="name">Name</MenuItem>
            <MenuItem value="size">Size</MenuItem>
            <MenuItem value="type">Type</MenuItem>
          </TextField>
          <TextField size="small" select label="Order" value={sortOrder} onChange={(e) => resetPage(setSortOrder)(e.target.value as "asc" | "desc")}>
            <MenuItem value="desc">Descending</MenuItem>
            <MenuItem value="asc">Ascending</MenuItem>
          </TextField>
          <Button onClick={clearFilters}>Clear filters</Button>
        </CardContent>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      <Card>
        {loading && <LinearProgress />}
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell align="right">Size</TableCell>
                <TableCell>Uploaded</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Duplicate</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data?.items.map((f) => (
                <TableRow key={f.id} hover>
                  <TableCell sx={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      {f.is_protected && <LockIcon fontSize="inherit" color="warning" />}
                      <span title={f.original_filename}>{f.original_filename}</span>
                    </Box>
                  </TableCell>
                  <TableCell>{f.category}</TableCell>
                  <TableCell align="right">{formatBytes(f.size_bytes)}</TableCell>
                  <TableCell>{formatDate(f.uploaded_at)}</TableCell>
                  <TableCell>{statusChip(f)}</TableCell>
                  <TableCell>{duplicateChip(f)}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    <Tooltip title="Details">
                      <IconButton size="small" onClick={() => setDetailsId(f.id)}>
                        <InfoIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Download">
                      <IconButton size="small" onClick={() => void handleDownload(f)}>
                        <DownloadIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={f.is_protected ? "Remove protection" : "Protect from deletion"}>
                      <IconButton size="small" onClick={() => void toggleProtect(f)}>
                        {f.is_protected ? <LockOpenIcon fontSize="small" /> : <LockIcon fontSize="small" />}
                      </IconButton>
                    </Tooltip>
                    {(f.status === "failed" || f.status === "pending") && (
                      <Tooltip title="Re-run analysis">
                        <IconButton size="small" onClick={() => void reprocess(f)}>
                          <RefreshIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                    <Tooltip title="Delete">
                      <IconButton size="small" color="error" onClick={() => setDeleteId(f.id)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {data && data.items.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 5, color: "text.secondary" }}>
                    No files match your filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={data?.total ?? 0}
          page={Math.max(page - 1, 0)}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[10, 25, 50, 100]}
          onPageChange={(_, p) => setPage(p + 1)}
          onRowsPerPageChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
        />
      </Card>

      <FileDetailsDialog fileId={detailsId} onClose={() => setDetailsId(null)} />
      <DeleteFileDialog
        fileId={deleteId}
        onClose={() => setDeleteId(null)}
        onDeleted={(freed, name) => {
          setDeleteId(null);
          setNotice({ type: "success", text: `Deleted ${name}. Freed ${formatBytes(freed)}.` });
          void load(true);
        }}
      />
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
