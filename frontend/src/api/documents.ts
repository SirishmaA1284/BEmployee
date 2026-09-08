import { apiClient } from "./client";
import type { DocumentDetail, DocumentRead, RAGQueryResponse } from "../types/domain";

export async function listDocuments() {
  const { data } = await apiClient.get<DocumentRead[]>("/api/documents");
  return data;
}

export async function uploadDocument(file: File, title?: string) {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const { data } = await apiClient.post<DocumentRead>("/api/documents", form);
  return data;
}

export async function getDocument(documentId: string) {
  const { data } = await apiClient.get<DocumentDetail>(`/api/documents/${documentId}`);
  return data;
}

export async function deleteDocument(documentId: string) {
  await apiClient.delete(`/api/documents/${documentId}`);
}

export async function queryDocuments(query: string, topK = 4) {
  const { data } = await apiClient.post<RAGQueryResponse>("/api/documents/query", {
    query,
    top_k: topK,
  });
  return data;
}