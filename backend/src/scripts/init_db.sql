-- Initialize PostgreSQL database with pgvector extension
-- This script runs automatically when the database container starts

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Set timezone
SET timezone = 'UTC';

-- Grant all privileges on the database
GRANT ALL PRIVILEGES ON DATABASE helios TO heliosuser;

-- Grant privileges on public schema
GRANT ALL PRIVILEGES ON SCHEMA public TO heliosuser;

-- Grant default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO heliosuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO heliosuser;

