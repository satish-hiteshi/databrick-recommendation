import { useState, useRef, useEffect } from "react";
import { FiSend } from "react-icons/fi";
import { postQuery } from "../api/client";
import { patchResponse } from "../api/patchResults";
import ResultCard from "./ResultCard";
import type { ChatMessage, QueryResult, QueryResponse } from "../types";
import "./ChatTab.css";

interface Props {
  onEntitySelect: (result: QueryResult) => void;
}

const MODE_COLORS: Record<string, string> = {
  entity_single: "#10b981",
  entity_multi: "#3b82f6",
  theme_based: "#f59e0b",
  descriptive: "#8b5cf6",
  mixed: "#ef4444",
};

export default function ChatTab({ onEntitySelect }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async () => {
    const query = input.trim();
    if (!query || loading) return;

    const userMsg: ChatMessage = { id: Date.now().toString(), type: "user", text: query };
    const loadingMsg: ChatMessage = { id: (Date.now() + 1).toString(), type: "system", loading: true };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setLoading(true);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      const raw = await postQuery(query);
      const response = patchResponse(raw);
      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? { ...m, loading: false, response } : m))
      );
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? { ...m, loading: false, error: err?.message || "Request failed" }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleTextareaInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  };

  return (
    <div className="chat-tab">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <h2>Entertainment Discovery</h2>
            <p>Ask about games, movies, or TV shows you'd enjoy based on your tastes.</p>
            <div className="chat-examples">
              {[
                "Games like Elden Ring Nightreign",
                "Horror content across all categories",
                "Movies for fans of Resident Evil and Silent Hill",
                "I want dark fantasy but not comedy",
              ].map((q) => (
                <button key={q} className="example-btn" onClick={() => { setInput(q); textareaRef.current?.focus(); }}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-msg-${msg.type}`}>
            {msg.type === "user" && <div className="msg-bubble user-bubble">{msg.text}</div>}
            {msg.type === "system" && msg.loading && (
              <div className="msg-loading">
                <div className="loading-dots"><span /><span /><span /></div>
                <span>Searching...</span>
              </div>
            )}
            {msg.type === "system" && msg.error && (
              <div className="msg-error">Something went wrong: {msg.error}</div>
            )}
            {msg.type === "system" && msg.response && (
              <SystemResponse response={msg.response} onEntitySelect={onEntitySelect} />
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Ask me about entertainment... e.g., Movies similar to Elden Ring"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onInput={handleTextareaInput}
            onKeyDown={handleKeyDown}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={handleSubmit}
            disabled={!input.trim() || loading}
          >
            <FiSend size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

function SystemResponse({
  response,
  onEntitySelect,
}: {
  response: QueryResponse;
  onEntitySelect: (r: QueryResult) => void;
}) {
  const [activeVert, setActiveVert] = useState<string | null>(null);
  const intent = response.parsed_intent;
  const hasMultiVert = Object.keys(response.results_by_vertical || {}).length > 0;
  const verts = Object.keys(response.results_by_vertical || {});
  const currentVert = activeVert || verts[0];

  const results = hasMultiVert
    ? response.results_by_vertical[currentVert] || []
    : response.results || [];

  const t = response.timings;

  if (response.status !== "success") {
    return <div className="msg-error">{response.error || "No results found"}</div>;
  }

  return (
    <div className="system-response">
      <div className="response-header">
        <span
          className="mode-badge"
          style={{ background: MODE_COLORS[response.query_mode] || "#6b7280" }}
        >
          {response.query_mode}
        </span>
        <span className="intent-summary">
          {intent.positive_entities?.length > 0 && (
            <>Anchor: {intent.positive_entities.join(", ")}</>
          )}
          {intent.additional_keywords?.length > 0 && (
            <> | Keywords: {intent.additional_keywords.join(", ")}</>
          )}
          {" | "}Target: {intent.target_verticals?.join(", ")}
        </span>
        {response.date_filter_applied && response.date_filter_description && (
          <span className="date-filter-badge">
            &#128197; Filtered: {response.date_filter_description}
          </span>
        )}
      </div>

      {response.anchor_entities_resolved?.length > 0 && (
        <div className="resolved-chips">
          {response.anchor_entities_resolved.map((e, i) => (
            <span key={i} className="resolved-chip">{e}</span>
          ))}
          {response.negative_entities_resolved?.map((e, i) => (
            <span key={`neg-${i}`} className="resolved-chip neg">{e}</span>
          ))}
        </div>
      )}

      {hasMultiVert && (
        <div className="vert-tabs">
          {verts.map((v) => (
            <button
              key={v}
              className={`vert-tab ${currentVert === v ? "active" : ""}`}
              onClick={() => setActiveVert(v)}
            >
              {v === "game" ? "Games" : v === "movie" ? "Movies" : "TV Shows"}
              <span className="vert-tab-count">{(response.results_by_vertical[v] || []).length}</span>
            </button>
          ))}
        </div>
      )}

      <div className="results-list">
        {results.map((r) => (
          <ResultCard key={`${r.rank}-${r.name}`} result={r} onClick={() => onEntitySelect(r)} />
        ))}
        {results.length === 0 && <div className="no-results">No results for this vertical</div>}
      </div>

      {t && (
        <div className="latency-bar">
          <span className="latency-icon">&#9889;</span>
          <span>{t.total_ms?.toFixed(0)}ms</span>
          <span className="latency-detail">
            NLU: {t.nlu_ms?.toFixed(0)}ms | Retrieval: {t.retrieval_ms?.toFixed(0)}ms
            | Filter: {t.filter_ms?.toFixed(0)}ms | Rerank: {t.rerank_ms?.toFixed(0)}ms
          </span>
        </div>
      )}
    </div>
  );
}
