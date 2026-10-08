import {
  Alert,
  Box,
  Card,
  Chip,
  LinearProgress,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { analyticsApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { AuditRecord, DeletionRecord, Page } from "../api/types";
import { formatBytes, formatDate, shortHash } from "../utils/format";

export default function History() {
  const [tab, setTab] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [deletions, setDeletions] = useState<Page<DeletionRecord> | null>(null);
  const [audit, setAudit] = useState<Page<AuditRecord> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const request = tab === 0 ? analyticsApi.deletions(page + 1, pageSize).then(setDeletions) : analyticsApi.audit(page + 1, pageSize).then(setAudit);
    request
      .then(() => {
        if (!cancelled) setError(null);
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
  }, [tab, page, pageSize]);

  const total = tab === 0 ? deletions?.total ?? 0 : audit?.total ?? 0;

  return (
    <Box sx={{ display: "grid", gap: 2 }}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        History &amp; audit
      </Typography>
      <Tabs value={tab} onChange={(_, v: number) => { setTab(v); setPage(0); }}>
        <Tab label="Deletion history" />
        <Tab label="Audit log" />
      </Tabs>
      {error && <Alert severity="error">{error}</Alert>}
      <Card>
        {loading && <LinearProgress />}
        <TableContainer>
          {tab === 0 ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Deleted</TableCell>
                  <TableCell>Filename</TableCell>
                  <TableCell>Kind</TableCell>
                  <TableCell align="right">Storage freed</TableCell>
                  <TableCell>SHA-256</TableCell>
                  <TableCell>Reason</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {deletions?.items.map((d) => (
                  <TableRow key={d.id} hover>
                    <TableCell>{formatDate(d.deleted_at)}</TableCell>
                    <TableCell>{d.filename}</TableCell>
                    <TableCell>{d.was_duplicate ? <Chip size="small" color="warning" label="Duplicate" /> : <Chip size="small" variant="outlined" label="File" />}</TableCell>
                    <TableCell align="right">{formatBytes(d.storage_freed)}</TableCell>
                    <TableCell sx={{ fontFamily: "monospace" }}>{shortHash(d.sha256)}</TableCell>
                    <TableCell>{d.reason ?? "-"}</TableCell>
                  </TableRow>
                ))}
                {deletions && deletions.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4, color: "text.secondary" }}>
                      No deletions recorded yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Time</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Entity</TableCell>
                  <TableCell>Details</TableCell>
                  <TableCell>IP</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {audit?.items.map((a) => (
                  <TableRow key={a.id} hover>
                    <TableCell>{formatDate(a.created_at)}</TableCell>
                    <TableCell>
                      <Chip size="small" label={a.action} />
                    </TableCell>
                    <TableCell>{a.entity_type ? `${a.entity_type} #${a.entity_id ?? "-"}` : "-"}</TableCell>
                    <TableCell sx={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "monospace", fontSize: 12 }}>
                      {a.details ? JSON.stringify(a.details) : "-"}
                    </TableCell>
                    <TableCell>{a.ip_address ?? "-"}</TableCell>
                  </TableRow>
                ))}
                {audit && audit.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 4, color: "text.secondary" }}>
                      No audit entries yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </TableContainer>
        <TablePagination
          component="div"
          count={total}
          page={page}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[10, 25, 50]}
          onPageChange={(_, p) => setPage(p)}
          onRowsPerPageChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(0);
          }}
        />
      </Card>
    </Box>
  );
}
