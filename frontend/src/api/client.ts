import axios from "axios";
import type {
  QueryResponse,
  EntityDetail,
  HistoryEntry,
  Stats,
} from "../types";

const api = axios.create({
  baseURL: `http://${window.location.hostname}:8000`,
});

export async function postQuery(query: string): Promise<QueryResponse> {
  const { data } = await api.post<QueryResponse>("/api/query", { query });
  return data;
}

export async function getHistory(): Promise<{ history: HistoryEntry[]; count: number }> {
  const { data } = await api.get("/api/history");
  return data;
}

export async function getHistoryDetail(id: number) {
  const { data } = await api.get(`/api/history/${id}`);
  return data;
}

export async function clearHistory(): Promise<void> {
  await api.delete("/api/history");
}

export async function getEntities(params: {
  vertical?: string;
  search?: string;
  page?: number;
  page_size?: number;
}): Promise<{
  entities: EntityDetail[];
  total_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}> {
  const { data } = await api.get("/api/entities", { params });
  return data;
}

export async function getEntity(entityId: string): Promise<EntityDetail> {
  const { data } = await api.get(`/api/entities/${encodeURIComponent(entityId)}`);
  return data;
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get("/api/stats");
  return data;
}
