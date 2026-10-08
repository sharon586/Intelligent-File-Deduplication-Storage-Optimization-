import { Alert, Box, Card, CardContent, CircularProgress, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import FolderIcon from "@mui/icons-material/Folder";
import SavingsIcon from "@mui/icons-material/Savings";
import StorageIcon from "@mui/icons-material/Storage";
import { ArcElement, BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip } from "chart.js";
import { useEffect, useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import { analyticsApi } from "../api/endpoints";
import { getErrorMessage } from "../api/client";
import type { AnalyticsSummary, FileBrief } from "../api/types";
import StatCard from "../components/StatCard";
import { formatBytes, formatDate } from "../utils/format";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const PALETTE = ["#2f5bea", "#00897b", "#f9a825", "#e53935", "#8e24aa", "#6d4c41", "#546e7a"];

function FileTable({ title, files }: { title: string; files: FileBrief[] }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
          {title}
        </Typography>
        {files.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No files yet.
          </Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell align="right">Size</TableCell>
                <TableCell>Uploaded</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {files.map((f) => (
                <TableRow key={f.id}>
                  <TableCell sx={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {f.original_filename}
                  </TableCell>
                  <TableCell align="right">{formatBytes(f.size_bytes)}</TableCell>
                  <TableCell>{formatDate(f.uploaded_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      analyticsApi
        .summary()
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => {
          if (!cancelled) setError(getErrorMessage(e));
        });
    load();
    const timer = window.setInterval(load, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (error && !data) return <Alert severity="error">{error}</Alert>;
  if (!data) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  const uniqueStorage = Math.max(data.total_storage - data.potential_savings, 0);

  return (
    <Box sx={{ display: "grid", gap: 3 }}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        Storage dashboard
      </Typography>
      {error && <Alert severity="warning">{error}</Alert>}
      {data.pending_files > 0 && (
        <Alert severity="info">{data.pending_files} file(s) are still being analysed in the background.</Alert>
      )}

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}>
        <StatCard label="Total files" value={data.total_files.toLocaleString()} icon={<FolderIcon fontSize="small" />} />
        <StatCard label="Total storage" value={formatBytes(data.total_storage)} icon={<StorageIcon fontSize="small" />} />
        <StatCard
          label="Duplicate files"
          value={data.duplicate_files.toLocaleString()}
          hint={`${data.duplicate_groups} duplicate group(s)`}
          icon={<ContentCopyIcon fontSize="small" />}
          color="warning.main"
        />
        <StatCard
          label="Duplicate storage"
          value={formatBytes(data.duplicate_storage)}
          hint="All files that belong to a duplicate group"
          icon={<StorageIcon fontSize="small" />}
          color="warning.main"
        />
        <StatCard
          label="Potential savings"
          value={formatBytes(data.potential_savings)}
          hint={`${data.savings_percent}% of total storage`}
          icon={<SavingsIcon fontSize="small" />}
          color="success.main"
        />
      </Box>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <Card>
          <CardContent>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
              Storage by category
            </Typography>
            {data.by_category.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Upload files to see the breakdown.
              </Typography>
            ) : (
              <Box sx={{ height: 260, display: "grid", placeItems: "center" }}>
                <Doughnut
                  data={{
                    labels: data.by_category.map((c) => c.category),
                    datasets: [{ data: data.by_category.map((c) => c.size_bytes), backgroundColor: PALETTE }],
                  }}
                  options={{
                    maintainAspectRatio: false,
                    plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${formatBytes(Number(ctx.raw))}` } } },
                  }}
                />
              </Box>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
              Unique vs redundant storage
            </Typography>
            {data.total_storage === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No data yet.
              </Typography>
            ) : (
              <Box sx={{ height: 260, display: "grid", placeItems: "center" }}>
                <Doughnut
                  data={{
                    labels: ["Needed storage", "Redundant copies"],
                    datasets: [{ data: [uniqueStorage, data.potential_savings], backgroundColor: ["#2f5bea", "#e53935"] }],
                  }}
                  options={{
                    maintainAspectRatio: false,
                    plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${formatBytes(Number(ctx.raw))}` } } },
                  }}
                />
              </Box>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
              Uploads (last 14 days)
            </Typography>
            <Box sx={{ height: 260 }}>
              <Bar
                data={{
                  labels: data.uploads_by_day.map((d) => d.date.slice(5)),
                  datasets: [{ label: "Uploads", data: data.uploads_by_day.map((d) => d.count), backgroundColor: "#00897b" }],
                }}
                options={{
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                }}
              />
            </Box>
          </CardContent>
        </Card>
      </Box>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
        <FileTable title="Largest files" files={data.largest_files} />
        <FileTable title="Recent uploads" files={data.recent_uploads} />
      </Box>
    </Box>
  );
}
