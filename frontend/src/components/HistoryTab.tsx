import { useEffect, useState, useCallback } from "react";
import { FiClock, FiTrash2, FiSearch, FiArrowLeft, FiChevronDown } from "react-icons/fi";
import { getHistory, getHistoryDetail, clearHistory } from "../api/client";
import ResultCard from "./ResultCard";
import type { HistoryEntry, QueryResult, QueryResponse } from "../types";
import "./HistoryTab.css";

const MODE_COLORS: Record<string, string> = {
  entity_single: "#10b981",
  entity_multi: "#3b82f6",
  theme_based: "#f59e0b",
  descriptive: "#8b5cf6",
  mixed: "#ef4444",
};

interface Props {
  onEntitySelect: (result: QueryResult) => void;
}

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function HistoryTab({ onEntitySelect }: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [fetched, setFetched] = useState(false);

  // Detail view state
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailData, setDetailData] = useState<QueryResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailEntry, setDetailEntry] = useState<HistoryEntry | null>(null);

  const fetchEntries = useCallback(() => {
    setLoading(true);
    getHistory()
      .then((res) => setEntries(res.history))
      .catch(console.error)
      .finally(() => { setLoading(false); setFetched(true); });
  }, []);

  useEffect(() => {
    if (!fetched) fetchEntries();
  }, [fetched, fetchEntries]);

  const handleRowClick = async (entry: HistoryEntry) => {
    setSelectedId(entry.id);
    setDetailEntry(entry);
    setDetailData(null);
    setDetailLoading(true);
    try {
      const detail = await getHistoryDetail(entry.id);
      setDetailData(detail.results || detail);
    } catch {
      setDetailData(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleBack = () => {
    setSelectedId(null);
    setDetailData(null);
    setDetailEntry(null);
  };

  const handleClear = async () => {
    await clearHistory();
    setEntries([]);
    setConfirmClear(false);
    handleBack();
  };

  const filtered = entries.filter((e) => {
    if (searchText && !e.query_text.toLowerCase().includes(searchText.toLowerCase())) return false;
    if (modeFilter && e.parsed_intent?.query_mode !== modeFilter) return false;
    return true;
  });

  const modes = Array.from(new Set(entries.map((e) => e.parsed_intent?.query_mode).filter(Boolean)));

  // ── Detail View ──
  if (selectedId !== null && detailEntry) {
    return (
      <HistoryDetailView
        entry={detailEntry}
        data={detailData}
        loading={detailLoading}
        onBack={handleBack}
        onEntitySelect={onEntitySelect}
      />
    );
  }

  // ── List View ──
  return (
    <div className="history-tab">
      <div className="tab-header">
        <h2>Query History</h2>
        <div className="header-actions">
          <button className="refresh-btn" onClick={fetchEntries}>Refresh</button>
          {!confirmClear ? (
            <button className="clear-btn" onClick={() => setConfirmClear(true)}>
              <FiTrash2 size={14} /> Clear
            </button>
          ) : (
            <div className="confirm-clear">
              <span>Clear all?</span>
              <button className="confirm-yes" onClick={handleClear}>Yes</button>
              <button className="confirm-no" onClick={() => setConfirmClear(false)}>No</button>
            </div>
          )}
        </div>
      </div>

      <div className="history-filters">
        <div className="history-search">
          <FiSearch size={14} />
          <input
            placeholder="Search queries..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>
        <select
          className="mode-select"
          value={modeFilter}
          onChange={(e) => setModeFilter(e.target.value)}
        >
          <option value="">All modes</option>
          {modes.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {loading && <div className="tab-loading">Loading history...</div>}

      {!loading && entries.length === 0 && (
        <div className="tab-empty"><FiClock size={32} /><p>No queries yet. Try the Chat tab!</p></div>
      )}

      <div className="history-table-wrap">
        {filtered.length > 0 && (
          <table className="history-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Query</th>
                <th>Mode</th>
                <th>Results</th>
                <th>Latency</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, idx) => {
                const mode = entry.parsed_intent?.query_mode || "—";
                const modeColor = MODE_COLORS[mode] || "#6b7280";
                const queryShort = entry.query_text.length > 60
                  ? entry.query_text.slice(0, 60) + "..."
                  : entry.query_text;
                return (
                  <tr key={entry.id} className="history-row" onClick={() => handleRowClick(entry)}>
                    <td className="col-num">{idx + 1}</td>
                    <td className="col-query" title={entry.query_text}>{queryShort}</td>
                    <td><span className="mode-badge-sm" style={{ background: modeColor }}>{mode}</span></td>
                    <td className="col-center">{entry.result_count}</td>
                    <td className="col-center">{entry.latency_ms?.toFixed(0)}ms</td>
                    <td className="col-time">{relativeTime(entry.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Full-page detail view ──

function HistoryDetailView({
  entry,
  data,
  loading,
  onBack,
  onEntitySelect,
}: {
  entry: HistoryEntry;
  data: QueryResponse | null;
  loading: boolean;
  onBack: () => void;
  onEntitySelect: (r: QueryResult) => void;
}) {
  const intent = entry.parsed_intent;
  const [nluOpen, setNluOpen] = useState(false);

  return (
    <div className="history-detail">
      <div className="detail-breadcrumb">
        <button className="back-btn" onClick={onBack}>
          <FiArrowLeft size={16} /> Query History
        </button>
      </div>

      {/* User bubble */}
      <div className="detail-user-bubble-wrap">
        <div className="detail-user-bubble">{entry.query_text}</div>
      </div>

      {/* Collapsible NLU */}
      <button className="nlu-toggle" onClick={() => setNluOpen(!nluOpen)}>
        <FiChevronDown size={14} style={{ transform: nluOpen ? "rotate(180deg)" : "none", transition: "150ms ease" }} />
        NLU Analysis
        <span className="nlu-toggle-mode" style={{ background: MODE_COLORS[intent?.query_mode] || "#6b7280" }}>
          {intent?.query_mode}
        </span>
      </button>
      {nluOpen && (
        <div className="nlu-details">
          <div className="nlu-grid">
            <NluField label="Type" value={intent?.query_type} />
            <NluField label="Verticals" value={intent?.target_verticals?.join(", ")} />
            {intent?.positive_entities?.length > 0 && <NluField label="Positive" value={intent.positive_entities.join(", ")} />}
            {intent?.negative_entities?.length > 0 && <NluField label="Negative" value={intent.negative_entities.join(", ")} />}
            {intent?.additional_keywords?.length > 0 && <NluField label="Keywords" value={intent.additional_keywords.join(", ")} />}
            {intent?.description_derived_keywords?.length > 0 && <NluField label="Derived" value={intent.description_derived_keywords.join(", ")} />}
          </div>
        </div>
      )}

      {loading && <div className="tab-loading">Loading results...</div>}

      {data && (
        <>
          {/* Resolved entities */}
          {data.anchor_entities_resolved?.length > 0 && (
            <div className="detail-chips-row">
              {data.anchor_entities_resolved.map((e, i) => (
                <span key={i} className="resolved-chip">{e}</span>
              ))}
              {data.negative_entities_resolved?.map((e, i) => (
                <span key={`neg-${i}`} className="resolved-chip neg">{e}</span>
              ))}
            </div>
          )}

          {/* Results */}
          {data.results_by_vertical && Object.keys(data.results_by_vertical).length > 0 ? (
            Object.entries(data.results_by_vertical).map(([vert, results]) => (
              <div key={vert} className="detail-vert-section">
                <h3 className="detail-vert-title">
                  {vert === "game" ? "Games" : vert === "movie" ? "Movies" : "TV Shows"}
                  <span className="detail-vert-count">{results.length}</span>
                </h3>
                <div className="results-list">
                  {results.map((r) => (
                    <ResultCard key={`${r.rank}-${r.name}`} result={r} onClick={() => onEntitySelect(r)} />
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div className="results-list">
              {(data.results || []).map((r) => (
                <ResultCard key={`${r.rank}-${r.name}`} result={r} onClick={() => onEntitySelect(r)} />
              ))}
            </div>
          )}

          {/* Latency footer */}
          {data.timings && (
            <div className="latency-bar">
              <span className="latency-icon">&#9889;</span>
              <span>{data.timings.total_ms?.toFixed(0)}ms</span>
              <span className="latency-detail">
                NLU: {data.timings.nlu_ms?.toFixed(0)}ms | Retrieval: {data.timings.retrieval_ms?.toFixed(0)}ms
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function NluField({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="nlu-field">
      <span className="nlu-label">{label}</span>
      <span className="nlu-value">{value}</span>
    </div>
  );
}
