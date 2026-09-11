import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { deleteDocument, listDocuments, queryDocuments, uploadDocument } from "../api/documents";
import { PageLayout } from "../components/PageLayout";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KiB`;
}

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!selectedFile) return Promise.reject(new Error("No file selected"));
      return uploadDocument(selectedFile);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedFile(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const queryMutation = useMutation({
    mutationFn: () => queryDocuments(question),
    onSuccess: () => setQuestion(""),
  });

  function handleUpload(event: FormEvent) {
    event.preventDefault();
    uploadMutation.mutate();
  }

  function handleAsk(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    queryMutation.mutate();
  }

  const result = queryMutation.data;

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Documents</h1>
      <p className="text-sm text-slate-500">
        Upload business documents (text, markdown, CSV, JSON, PDF, DOCX). They are chunked,
        embedded, and searchable by the AI Employee via RAG.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">Upload a document</h2>
        <form onSubmit={handleUpload} className="flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept=".txt,.md,.csv,.json,.pdf,.docx"
            onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
          <button
            type="submit"
            disabled={!selectedFile || uploadMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {uploadMutation.isPending ? "Uploading…" : "Upload"}
          </button>
        </form>
        {uploadMutation.isError && (
          <p className="mt-2 text-sm text-red-600">
            Upload failed. Use a .txt/.md/.csv/.json/.pdf/.docx file under 2 MiB.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">Ask your documents</h2>
        <form onSubmit={handleAsk} className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='e.g. "What does our return policy say?"'
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!question.trim() || queryMutation.isPending}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {queryMutation.isPending ? "Asking…" : "Ask"}
          </button>
        </form>
        {result && (
          <div className="mt-4">
            <p className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm">{result.answer}</p>
            {result.sources.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-medium text-slate-500">Sources ({result.sources.length})</p>
                <ul className="mt-1 flex flex-wrap gap-2">
                  {result.sources.map((source) => (
                    <li
                      key={`${source.document_id}-${source.chunk_index}`}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                    >
                      {source.document_name} · chunk {source.chunk_index} · {Math.round(source.similarity * 100)}%
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Uploaded documents</h2>
        {documentsQuery.data?.length === 0 ? (
          <p className="text-sm text-slate-500">No documents uploaded yet.</p>
        ) : (
          <ul className="space-y-2">
            {documentsQuery.data?.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm"
              >
                <div className="min-w-0">
                  <p className="font-medium">{doc.filename}</p>
                  <p className="text-xs text-slate-500">
                    {doc.content_type} · {formatBytes(doc.size_bytes)}
                    {doc.processed_at && ` · processed ${new Date(doc.processed_at).toLocaleString()}`}
                  </p>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(doc.id)}
                  disabled={deleteMutation.isPending}
                  className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </PageLayout>
  );
}