import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { FiClock, FiTrash2, FiSearch } from "react-icons/fi";
import { getHistory, clearHistory } from "../api/client";
import type { HistoryEntry } from "../types";
import "./HistoryList.css";

const MODE_COLORS: Record<string, string> = {
  entity_single: "#10b981",
  entity_multi: "#3b82f6",
  theme_based: "#f59e0b",
  descriptive: "#8b5cf6",
  mixed: "#ef4444",
};

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (diff < 1) return "Just now";
  if (diff < 60) return `${diff}m ago`;
  const hrs = Math.floor(diff / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function HistoryList() {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);

  const fetchEntries = useCallback(() => {
    setLoading(true);
    getHistory()
      .then((res) => setEntries(res.history))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const handleClear = async () => {
    await clearHistory();
    setEntries([]);
    setConfirmClear(false);
  };

  const filtered = entries.filter((e) => {
    if (searchText && !e.query_text.toLowerCase().includes(searchText.toLowerCase())) return false;
    if (modeFilter && e.parsed_intent?.query_mode !== modeFilter) return false;
    return true;
  });

  const modes = Array.from(new Set(entries.map((e) => e.parsed_intent?.query_mode).filter(Boolean)));

  return (
    <div className="history-list-page">
      <div className="hl-header">
        <h2>Query History</h2>
        <div className="hl-actions">
          <button className="hl-btn" onClick={fetchEntries}>Refresh</button>
          {!confirmClear ? (
            <button className="hl-btn hl-btn-danger" onClick={() => setConfirmClear(true)}>
              <FiTrash2 size={13} /> Clear
            </button>
          ) : (
            <div className="hl-confirm">
              <span>Clear all?</span>
              <button className="hl-confirm-yes" onClick={handleClear}>Yes</button>
              <button className="hl-confirm-no" onClick={() => setConfirmClear(false)}>No</button>
            </div>
          )}
        </div>
      </div>

      <div className="hl-filters">
        <div className="hl-search">
          <FiSearch size={14} />
          <input placeholder="Search queries..." value={searchText} onChange={(e) => setSearchText(e.target.value)} />
        </div>
        <select className="hl-mode-select" value={modeFilter} onChange={(e) => setModeFilter(e.target.value)}>
          <option value="">All modes</option>
          {modes.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {loading && <div className="hl-empty">Loading...</div>}
      {!loading && entries.length === 0 && (
        <div className="hl-empty"><FiClock size={28} /><p>No queries yet. Try the Chat tab!</p></div>
      )}

      {filtered.length > 0 && (
        <div className="hl-table-wrap">
          <table className="hl-table">
            <thead>
              <tr>
                <th style={{ width: 48 }}>#</th>
                <th>Query</th>
                <th style={{ width: 120 }}>Mode</th>
                <th style={{ width: 140 }}>Verticals</th>
                <th style={{ width: 80 }}>Latency</th>
                <th style={{ width: 110 }}>Time</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, idx) => {
                const mode = entry.parsed_intent?.query_mode || "—";
                const verts = entry.parsed_intent?.target_verticals || [];
                const queryShort = entry.query_text.length > 70
                  ? entry.query_text.slice(0, 70) + "..."
                  : entry.query_text;
                return (
                  <tr key={entry.id} className="hl-row" onClick={() => navigate(`/history/${entry.id}`)}>
                    <td className="hl-num">{idx + 1}</td>
                    <td className="hl-query" title={entry.query_text}>{queryShort}</td>
                    <td>
                      <span className="hl-mode-badge" style={{ background: MODE_COLORS[mode] || "#6b7280" }}>
                        {mode}
                      </span>
                    </td>
                    <td className="hl-verts">
                      {verts.map((v) => (
                        <span key={v} className={`hl-vert-pill hl-vert-${v}`}>{v}</span>
                      ))}
                    </td>
                    <td className="hl-center">{entry.latency_ms?.toFixed(0)}ms</td>
                    <td className="hl-time">{relativeTime(entry.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
