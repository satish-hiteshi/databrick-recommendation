import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { FiArrowLeft, FiChevronDown } from "react-icons/fi";
import { getHistoryDetail } from "../api/client";
import { patchResponse } from "../api/patchResults";
import ResultCard from "./ResultCard";
import type { QueryResult, QueryResponse } from "../types";
import "./HistoryDetail.css";

const MODE_COLORS: Record<string, string> = {
  entity_single: "#10b981",
  entity_multi: "#3b82f6",
  theme_based: "#f59e0b",
  descriptive: "#8b5cf6",
  mixed: "#ef4444",
};

interface Props {
  onEntitySelect: (r: QueryResult) => void;
}

export default function HistoryDetail({ onEntitySelect }: Props) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<QueryResponse | null>(null);
  const [queryText, setQueryText] = useState("");
  const [loading, setLoading] = useState(true);
  const [nluOpen, setNluOpen] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getHistoryDetail(Number(id))
      .then((detail) => {
        setQueryText(detail.query_text || "");
        const raw = detail.results || detail;
        setData(patchResponse(raw));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const intent = data?.parsed_intent;

  return (
    <div className="hd-page">
      <button className="hd-back" onClick={() => navigate("/history")}>
        <FiArrowLeft size={16} /> Query History
      </button>

      {loading && <div className="hd-loading">Loading...</div>}

      {data && (
        <>
          {/* User bubble */}
          <div className="hd-bubble-wrap">
            <div className="hd-bubble">{queryText || data.query}</div>
          </div>

          {/* NLU collapsible */}
          <button className="hd-nlu-toggle" onClick={() => setNluOpen(!nluOpen)}>
            <FiChevronDown size={14} style={{ transform: nluOpen ? "rotate(180deg)" : "none", transition: "150ms" }} />
            NLU Analysis
            {intent?.query_mode && (
              <span className="hd-mode-pill" style={{ background: MODE_COLORS[intent.query_mode] || "#6b7280" }}>
                {intent.query_mode}
              </span>
            )}
          </button>
          {nluOpen && intent && (
            <div className="hd-nlu-body">
              <NluRow label="Type" value={intent.query_type} />
              <NluRow label="Verticals" value={intent.target_verticals?.join(", ")} />
              {intent.positive_entities?.length > 0 && <NluRow label="Positive" value={intent.positive_entities.join(", ")} />}
              {intent.negative_entities?.length > 0 && <NluRow label="Negative" value={intent.negative_entities.join(", ")} />}
              {intent.additional_keywords?.length > 0 && <NluRow label="Keywords" value={intent.additional_keywords.join(", ")} />}
              {intent.description_derived_keywords?.length > 0 && <NluRow label="Derived" value={intent.description_derived_keywords.join(", ")} />}
            </div>
          )}

          {/* Resolved entities */}
          {data.anchor_entities_resolved?.length > 0 && (
            <div className="hd-chips">
              {data.anchor_entities_resolved.map((e, i) => <span key={i} className="hd-chip pos">{e}</span>)}
              {data.negative_entities_resolved?.map((e, i) => <span key={`n${i}`} className="hd-chip neg">{e}</span>)}
            </div>
          )}

          {/* Results */}
          {data.results_by_vertical && Object.keys(data.results_by_vertical).length > 0 ? (
            Object.entries(data.results_by_vertical).map(([vert, results]) => (
              <div key={vert} className="hd-vert-section">
                <h3 className="hd-vert-title">
                  {vert === "game" ? "Games" : vert === "movie" ? "Movies" : "TV Shows"}
                  <span className="hd-vert-count">{results.length}</span>
                </h3>
                <div className="hd-results">
                  {results.map((r) => <ResultCard key={`${r.rank}-${r.name}`} result={r} onClick={() => onEntitySelect(r)} />)}
                </div>
              </div>
            ))
          ) : (
            <div className="hd-results">
              {(data.results || []).map((r) => <ResultCard key={`${r.rank}-${r.name}`} result={r} onClick={() => onEntitySelect(r)} />)}
            </div>
          )}

          {/* Latency */}
          {data.timings && (
            <div className="hd-latency">
              &#9889; {data.timings.total_ms?.toFixed(0)}ms
              <span className="hd-latency-detail">
                NLU {data.timings.nlu_ms?.toFixed(0)}ms &middot; Retrieval {data.timings.retrieval_ms?.toFixed(0)}ms
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function NluRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="hd-nlu-row">
      <span className="hd-nlu-label">{label}</span>
      <span className="hd-nlu-value">{value}</span>
    </div>
  );
}
