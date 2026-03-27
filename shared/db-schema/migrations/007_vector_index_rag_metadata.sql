-- 006_vector_index_rag_metadata.sql
-- 为完整 RAG 主链路扩展 vector_index 元数据列

ALTER TABLE vector_index ADD COLUMN doc_key TEXT;
ALTER TABLE vector_index ADD COLUMN source_type TEXT NOT NULL DEFAULT 'capture';
ALTER TABLE vector_index ADD COLUMN knowledge_id INTEGER;
ALTER TABLE vector_index ADD COLUMN time INTEGER;
ALTER TABLE vector_index ADD COLUMN start_time INTEGER;
ALTER TABLE vector_index ADD COLUMN end_time INTEGER;
ALTER TABLE vector_index ADD COLUMN app_name TEXT;
ALTER TABLE vector_index ADD COLUMN win_title TEXT;
ALTER TABLE vector_index ADD COLUMN category TEXT;
ALTER TABLE vector_index ADD COLUMN user_verified INTEGER NOT NULL DEFAULT 0;

UPDATE vector_index
SET doc_key = COALESCE(doc_key, 'capture:' || capture_id),
    source_type = COALESCE(source_type, 'capture'),
    time = COALESCE(time, created_at);

CREATE INDEX IF NOT EXISTS idx_vector_index_doc_key ON vector_index(doc_key);
CREATE INDEX IF NOT EXISTS idx_vector_index_source_type_time ON vector_index(source_type, time);
CREATE INDEX IF NOT EXISTS idx_vector_index_knowledge_id ON vector_index(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_vector_index_app_name ON vector_index(app_name);
