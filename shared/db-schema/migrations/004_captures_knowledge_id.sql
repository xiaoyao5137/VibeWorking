-- 004_captures_knowledge_id.sql
-- 为 captures 表添加 knowledge_id 外键，关联已提炼的知识条目

ALTER TABLE captures ADD COLUMN knowledge_id INTEGER;
