import { useState } from "react";
import type { QueryResult } from "../types";
import "./ResultCard.css";

const VERT_COLORS: Record<string, { bg: string; text: string; accent: string }> = {
  game: { bg: "#d1fae5", text: "#065f46", accent: "#10B981" },
  movie: { bg: "#dbeafe", text: "#1e40af", accent: "#3B82F6" },
  tv: { bg: "#fef3c7", text: "#92400e", accent: "#F59E0B" },
};

function barColor(pct: number): string {
  if (pct >= 80) return "#10B981";
  if (pct >= 60) return "#14B8A6";
  if (pct >= 40) return "#F59E0B";
  if (pct >= 20) return "#F97316";
  return "#EF4444";
}

function formatDate(d: string): { text: string; upcoming: boolean } {
  const date = new Date(d + "T00:00:00");
  const now = new Date();
  const upcoming = date > now;
  const text = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return { text, upcoming };
}

interface Props {
  result: QueryResult;
  onClick: () => void;
}

export default function ResultCard({ result, onClick }: Props) {
  const [showTooltip, setShowTooltip] = useState(false);
  const vert = VERT_COLORS[result.vertical] || { bg: "#f3f4f6", text: "#374151", accent: "#6b7280" };
  const pct = result.similarity_percentage ?? 0;
  const color = barColor(pct);
  const rd = result.release_date ? formatDate(result.release_date) : null;

  return (
    <div className="result-card" data-vertical={result.vertical} onClick={onClick}>
      <div className="result-rank">{result.rank}</div>
      <div className="result-body">
        <div className="result-top">
          <div className="result-name-col">
            <span className="result-name">{result.name}</span>
            {rd && (
              <span className={`result-date ${rd.upcoming ? "upcoming" : ""}`}>
                {rd.upcoming ? "Upcoming: " : ""}{rd.text}
              </span>
            )}
          </div>
          <span className="vert-badge" style={{ background: vert.bg, color: vert.text }}>
            {result.vertical}
          </span>
          {result.in_both_sets && <span className="dual-badge">Dual Signal</span>}
          <span className="match-pct" style={{ color }}>{pct}% Match</span>
        </div>

        <div className="score-bar-row">
          <div className="score-track">
            <div className="score-fill" style={{ width: `${pct}%`, background: color }} />
          </div>
        </div>

        <div className="signal-row">
          <span className="rrf-text">RRF: {(result.rrf_score ?? result.final_score).toFixed(4)}</span>
          <span className={`signal-indicator ${result.appeared_in_vector ? "sig-vec" : "sig-miss"}`}>
            Vector {result.appeared_in_vector ? `#${result.vector_rank} \u2713` : "\u2717"}
          </span>
          <span className={`signal-indicator ${result.appeared_in_bm25 ? "sig-bm25" : "sig-miss"}`}>
            BM25 {result.appeared_in_bm25 ? `#${result.bm25_rank} \u2713` : "\u2717"}
          </span>
          {result.appeared_in_searches > 1 && (
            <span className="signal-indicator sig-overlap">{result.appeared_in_searches} sources</span>
          )}
        </div>

        {result.shared_keywords.length > 0 && (
          <div className="result-keywords">
            {result.shared_keywords.slice(0, 6).map((kw) => (
              <span key={kw} className="kw-chip">{kw}</span>
            ))}
          </div>
        )}

        {result.reasoning_short && (
          <div
            className="reasoning-box"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
          >
            <span className="reasoning-icon">&#128161;</span>
            <span className="reasoning-text">{result.reasoning_short}</span>
            {showTooltip && result.reasoning_long && result.reasoning_long !== result.reasoning_short && (
              <div className="reasoning-tooltip">{result.reasoning_long}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
