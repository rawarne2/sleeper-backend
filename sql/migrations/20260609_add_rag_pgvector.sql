-- Phase 4 RAG: pgvector extension + document store for strategy KB and feedback corpus.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus       VARCHAR(40) NOT NULL,
  source_id    VARCHAR(64) NOT NULL,
  content      TEXT NOT NULL,
  metadata     JSONB NOT NULL DEFAULT '{}',
  embedding    vector(768) NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (corpus, source_id)
);

CREATE INDEX IF NOT EXISTS ix_rag_documents_corpus ON rag_documents(corpus);

CREATE INDEX IF NOT EXISTS ix_rag_documents_embedding
  ON rag_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 32);
