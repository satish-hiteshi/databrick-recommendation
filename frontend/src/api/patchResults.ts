import type { QueryResult, QueryResponse } from "../types";

/**
 * Compute similarity_percentage for results that are missing it
 * (e.g., older history entries saved before this field existed).
 * Top result in each list gets 100%, others scaled proportionally.
 */
export function patchSimilarityPct(results: QueryResult[]): QueryResult[] {
  if (!results || results.length === 0) return results;

  // Check if already patched
  if (results[0]?.similarity_percentage > 0) return results;

  const maxScore = Math.max(...results.map((r) => r.rrf_score ?? r.final_score ?? 0));
  if (maxScore <= 0) return results;

  return results.map((r) => ({
    ...r,
    rrf_score: r.rrf_score ?? r.final_score ?? 0,
    appeared_in_vector: r.appeared_in_vector ?? (r as any).in_both_sets ?? false,
    appeared_in_bm25: r.appeared_in_bm25 ?? (r as any).in_both_sets ?? false,
    vector_rank: r.vector_rank ?? null,
    bm25_rank: r.bm25_rank ?? null,
    similarity_percentage: Math.round(((r.rrf_score ?? r.final_score ?? 0) / maxScore) * 100),
  }));
}

/**
 * Patch an entire QueryResponse (handles both flat results and results_by_vertical).
 */
export function patchResponse(data: QueryResponse): QueryResponse {
  if (!data) return data;

  const patched = { ...data };

  if (patched.results?.length > 0) {
    patched.results = patchSimilarityPct(patched.results);
  }

  if (patched.results_by_vertical) {
    const patchedVert: Record<string, QueryResult[]> = {};
    for (const [vert, results] of Object.entries(patched.results_by_vertical)) {
      patchedVert[vert] = patchSimilarityPct(results);
    }
    patched.results_by_vertical = patchedVert;
  }

  return patched;
}
