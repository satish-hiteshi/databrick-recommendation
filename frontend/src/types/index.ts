export interface QueryResult {
  rank: number;
  name: string;
  vertical: string;
  final_score: number;
  rrf_score: number;
  vector_rank: number | null;
  bm25_rank: number | null;
  appeared_in_vector: boolean;
  appeared_in_bm25: boolean;
  in_both_sets: boolean;
  shared_keywords: string[];
  appeared_in_searches: number;
  negative_penalty: number;
  similarity_percentage: number;
  reasoning_short?: string;
  reasoning_long?: string;
  release_date?: string | null;
}

export interface ParsedIntent {
  query_mode: string;
  positive_entities: string[];
  negative_entities: string[];
  additional_keywords: string[];
  description_derived_keywords: string[];
  target_verticals: string[];
  query_type: string;
  date_filter_start?: string | null;
  date_filter_end?: string | null;
}

export interface Timings {
  nlu_ms: number;
  retrieval_ms: number;
  filter_ms: number;
  rerank_ms: number;
  total_ms: number;
}

export interface QueryResponse {
  query: string;
  parsed_intent: ParsedIntent;
  query_mode: string;
  anchor_entities_resolved: string[];
  negative_entities_resolved: string[];
  neg_filter_log: Array<{ name: string; action: string; reason: string }>;
  results: QueryResult[];
  results_by_vertical: Record<string, QueryResult[]>;
  timings: Timings;
  status: string;
  error?: string;
  history_id?: number;
  date_filter_applied?: boolean;
  date_filter_start?: string | null;
  date_filter_end?: string | null;
  date_filter_description?: string;
}

export interface EntityDetail {
  entity_id: string;
  name: string;
  vertical: string;
  description: string;
  composed_text: string;
  bm25_keywords: string[];
  franchise: string | null;
  developer: string | null;
  publisher: string | null;
  canonical_genres: string[];
  themes: string[];
  keywords: string[];
  release_date?: string | null;
}

export interface ChatMessage {
  id: string;
  type: "user" | "system";
  text?: string;
  response?: QueryResponse;
  loading?: boolean;
  error?: string;
}

export interface HistoryEntry {
  id: number;
  query_text: string;
  parsed_intent: ParsedIntent;
  result_count: number;
  latency_ms: number;
  created_at: string;
}

export interface Stats {
  total_entities: number;
  entities_by_vertical: Record<string, number>;
  total_queries: number;
  avg_latency_ms: number;
}
