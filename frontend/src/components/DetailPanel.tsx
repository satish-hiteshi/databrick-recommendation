import { useEffect, useState } from "react";
import { FiX } from "react-icons/fi";
import { getEntity } from "../api/client";
import type { SelectedEntity } from "../App";
import type { EntityDetail } from "../types";
import "./DetailPanel.css";

function pctColor(pct: number): string {
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
  entity: SelectedEntity | null;
  onClose: () => void;
}

export default function DetailPanel({ entity, onClose }: Props) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const open = entity !== null;

  useEffect(() => {
    if (!entity) {
      setDetail(null);
      return;
    }
    if (entity.detail) {
      setDetail(entity.detail);
      return;
    }
    if (entity.result) {
      setLoading(true);
      import("../api/client").then(({ getEntities }) => {
        getEntities({ search: entity.result!.name, page_size: 1 }).then((res) => {
          if (res.entities.length > 0) setDetail(res.entities[0]);
          setLoading(false);
        }).catch(() => setLoading(false));
      });
    }
  }, [entity]);

  const rd = (entity?.result?.release_date || detail?.release_date)
    ? formatDate((entity?.result?.release_date || detail?.release_date)!)
    : null;

  return (
    <>
      {open && <div className="detail-overlay" onClick={onClose} />}
      <aside className={`detail-panel ${open ? "open" : ""}`}>
        <button className="detail-close" onClick={onClose}><FiX size={20} /></button>

        {loading && <div className="detail-loading">Loading entity details...</div>}

        {detail && (
          <div className="detail-content">
            <h2 className="detail-name">{detail.name}</h2>
            <span
              className="detail-vert"
              style={{
                background: detail.vertical === "game" ? "#d1fae5" : detail.vertical === "movie" ? "#dbeafe" : "#fef3c7",
                color: detail.vertical === "game" ? "#065f46" : detail.vertical === "movie" ? "#1e40af" : "#92400e",
              }}
            >
              {detail.vertical}
            </span>

            {rd && (
              <span className={`detail-release-date ${rd.upcoming ? "upcoming" : ""}`}>
                {rd.upcoming ? "Upcoming: " : "Released: "}{rd.text}
              </span>
            )}

            {detail.description && (
              <p className="detail-desc">{detail.description}</p>
            )}

            {entity?.result?.reasoning_long && (
              <Section title="Why This Was Recommended">
                <div className="detail-reasoning">{entity.result.reasoning_long}</div>
              </Section>
            )}

            {detail.canonical_genres?.length > 0 && (
              <Section title="Genres">
                <Chips items={detail.canonical_genres} color="#dbeafe" textColor="#1e40af" />
              </Section>
            )}

            {detail.themes?.length > 0 && (
              <Section title="Themes">
                <Chips items={detail.themes} color="#ede9fe" textColor="#6d28d9" />
              </Section>
            )}

            {detail.bm25_keywords?.length > 0 && (
              <Section title="Keywords">
                <Chips items={detail.bm25_keywords} color="#f3f4f6" textColor="#374151" />
              </Section>
            )}

            {detail.franchise && (
              <Section title="Franchise">
                <span className="detail-meta-value">{detail.franchise}</span>
              </Section>
            )}

            {(detail.developer || detail.publisher) && (
              <Section title="Developer / Publisher">
                <span className="detail-meta-value">
                  {[detail.developer, detail.publisher].filter(Boolean).join(" / ")}
                </span>
              </Section>
            )}

            {entity?.result && (
              <Section title="Similarity">
                <div className="detail-match-pct" style={{ color: pctColor(entity.result.similarity_percentage ?? 0) }}>
                  {entity.result.similarity_percentage ?? 0}% Match
                </div>
                <div className="detail-scores">
                  <DetailScore
                    label="Match"
                    value={(entity.result.similarity_percentage ?? 0) / 100}
                    color={pctColor(entity.result.similarity_percentage ?? 0)}
                  />
                </div>
                <div style={{ fontSize: 11, color: "#94A3B8", fontFamily: "monospace", marginTop: 4 }}>
                  RRF: {(entity.result.rrf_score ?? entity.result.final_score).toFixed(4)}
                </div>
                <div className="detail-chips" style={{ marginTop: 8 }}>
                  <span className="detail-chip" style={{
                    background: entity.result.appeared_in_vector ? "#DBEAFE" : "#F1F5F9",
                    color: entity.result.appeared_in_vector ? "#1E40AF" : "#94A3B8",
                  }}>
                    Vector {entity.result.appeared_in_vector ? `#${entity.result.vector_rank} \u2713` : "\u2717"}
                  </span>
                  <span className="detail-chip" style={{
                    background: entity.result.appeared_in_bm25 ? "#EDE9FE" : "#F1F5F9",
                    color: entity.result.appeared_in_bm25 ? "#6D28D9" : "#94A3B8",
                  }}>
                    BM25 {entity.result.appeared_in_bm25 ? `#${entity.result.bm25_rank} \u2713` : "\u2717"}
                  </span>
                </div>
              </Section>
            )}

            {detail.composed_text && (
              <Section title="Composed Text">
                <div className="detail-composed">{detail.composed_text}</div>
              </Section>
            )}
          </div>
        )}
      </aside>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="detail-section">
      <h4 className="section-title">{title}</h4>
      {children}
    </div>
  );
}

function Chips({ items, color, textColor }: { items: string[]; color: string; textColor: string }) {
  return (
    <div className="detail-chips">
      {items.map((item) => (
        <span key={item} className="detail-chip" style={{ background: color, color: textColor }}>
          {item}
        </span>
      ))}
    </div>
  );
}

function DetailScore({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.min(Math.abs(value) * 100, 100);
  return (
    <div className="detail-score-row">
      <span className="detail-score-label">{label}</span>
      <div className="detail-score-track">
        <div className="detail-score-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="detail-score-value" style={{ color }}>
        {value >= 0 ? value.toFixed(3) : value.toFixed(3)}
      </span>
    </div>
  );
}
