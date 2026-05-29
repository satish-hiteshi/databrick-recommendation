import { useEffect, useState, useRef, useCallback } from "react";
import { FiSearch, FiChevronUp, FiChevronDown } from "react-icons/fi";
import { getEntities, getStats } from "../api/client";
import type { EntityDetail, Stats } from "../types";
import "./DatasetTab.css";

const VERT_CONFIG: Record<string, { emoji: string; label: string; bg: string; text: string }> = {
  "": { emoji: "", label: "All", bg: "var(--primary)", text: "white" },
  game: { emoji: "", label: "Games", bg: "#d1fae5", text: "#065f46" },
  movie: { emoji: "", label: "Movies", bg: "#dbeafe", text: "#1e40af" },
  tv: { emoji: "", label: "TV Shows", bg: "#fef3c7", text: "#92400e" },
};

interface Props {
  onEntitySelect: (detail: EntityDetail) => void;
}

export default function DatasetTab({ onEntitySelect }: Props) {
  const [entities, setEntities] = useState<EntityDetail[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [vertical, setVertical] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sortAsc, setSortAsc] = useState(true);
  const [fetched, setFetched] = useState(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>();

  const PAGE_SIZE = 50;

  const fetchEntities = useCallback((pg: number, vert: string, srch: string) => {
    setLoading(true);
    getEntities({
      vertical: vert || undefined,
      search: srch || undefined,
      page: pg,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        setEntities(res.entities);
        setTotalPages(res.total_pages);
        setTotalCount(res.total_count);
      })
      .catch(console.error)
      .finally(() => { setLoading(false); setFetched(true); });
  }, []);

  useEffect(() => {
    if (!fetched || vertical !== undefined || debouncedSearch !== undefined) {
      fetchEntities(page, vertical, debouncedSearch);
    }
  }, [page, vertical, debouncedSearch, fetchEntities]);

  useEffect(() => {
    getStats().then(setStats).catch(console.error);
  }, []);

  const handleSearchChange = (val: string) => {
    setSearch(val);
    clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(1);
    }, 350);
  };

  const handleVerticalChange = (v: string) => {
    setVertical(v);
    setPage(1);
  };

  const sorted = [...entities].sort((a, b) => {
    const cmp = a.name.localeCompare(b.name);
    return sortAsc ? cmp : -cmp;
  });

  const startIdx = (page - 1) * PAGE_SIZE + 1;
  const endIdx = Math.min(page * PAGE_SIZE, totalCount);

  return (
    <div className="dataset-tab">
      {/* Stats bar */}
      <div className="stats-bar">
        <h2>Entity Dataset</h2>
        {stats && (
          <div className="stats-badges">
            <span className="stats-total">{stats.total_entities.toLocaleString()} Entities</span>
            <span className="stats-badge" style={{ background: "#d1fae5", color: "#065f46" }}>
              {stats.entities_by_vertical.game} Games
            </span>
            <span className="stats-badge" style={{ background: "#dbeafe", color: "#1e40af" }}>
              {stats.entities_by_vertical.movie} Movies
            </span>
            <span className="stats-badge" style={{ background: "#fef3c7", color: "#92400e" }}>
              {stats.entities_by_vertical.tv} TV Shows
            </span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="dataset-controls">
        <div className="vert-filter">
          {(["", "game", "movie", "tv"] as const).map((v) => {
            const cfg = VERT_CONFIG[v];
            const isActive = vertical === v;
            const count = v === ""
              ? stats?.total_entities
              : stats?.entities_by_vertical[v];
            return (
              <button
                key={v}
                className={`filter-btn ${isActive ? "active" : ""}`}
                style={isActive ? { background: cfg.bg, color: cfg.text, borderColor: cfg.bg } : {}}
                onClick={() => handleVerticalChange(v)}
              >
                {cfg.label}
                {count !== undefined && <span className="filter-count">{count}</span>}
              </button>
            );
          })}
        </div>
        <div className="dataset-search">
          <FiSearch size={14} />
          <input
            placeholder="Search entities by name..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      <div className="dataset-table-wrap">
        {loading && entities.length === 0 && (
          <div className="tab-loading">Loading entities...</div>
        )}

        <table className="dataset-table">
          <thead>
            <tr>
              <th
                className="sortable"
                onClick={() => setSortAsc(!sortAsc)}
              >
                Name {sortAsc ? <FiChevronUp size={12} /> : <FiChevronDown size={12} />}
              </th>
              <th>Vertical</th>
              <th>Genres</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((e) => (
              <tr
                key={e.entity_id}
                className="entity-row"
                onClick={() => onEntitySelect(e)}
              >
                <td className="col-name">{e.name}</td>
                <td>
                  <span
                    className="vert-badge-sm"
                    style={{
                      background: e.vertical === "game" ? "#d1fae5" : e.vertical === "movie" ? "#dbeafe" : "#fef3c7",
                      color: e.vertical === "game" ? "#065f46" : e.vertical === "movie" ? "#1e40af" : "#92400e",
                    }}
                  >
                    {e.vertical}
                  </span>
                </td>
                <td className="col-genres">
                  {(e.canonical_genres || []).slice(0, 3).map((g) => (
                    <span key={g} className="genre-chip">{g}</span>
                  ))}
                  {(e.canonical_genres || []).length > 3 && (
                    <span className="genre-more">+{e.canonical_genres.length - 3}</span>
                  )}
                </td>
                <td className="col-desc">
                  {e.description
                    ? e.description.length > 80
                      ? e.description.slice(0, 80) + "..."
                      : e.description
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 0 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="pagination-info">
            Showing {startIdx}-{endIdx} of {totalCount.toLocaleString()}
            {vertical && ` ${VERT_CONFIG[vertical]?.label?.toLowerCase() || vertical}`}
          </span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}
