-- Create ats_user if it doesn't exist
DO
$$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ats_user'
   ) THEN
      CREATE ROLE ats_user LOGIN PASSWORD 'good_password';
   END IF;
END
$$;

-- Ensure ats_optimizer database exists
DO
$$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'ats_optimizer'
   ) THEN
      CREATE DATABASE ats_optimizer OWNER ats_user;
   END IF;
END
$$;

-- Connect to ats_optimizer database
\connect ats_optimizer

-- Create users table if not exists
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    resume_txt TEXT,
    linkedin_txt TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create jobs table if not exists
-- add a job_title with return from OLLAMA LATER! (job_title TEXT,)
CREATE TABLE IF NOT EXISTS jobs (
    job_id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id),
    job_description TEXT,
    generated_cv JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    chat_history JSONB
);

-- Trigger to update last_modified automatically
CREATE OR REPLACE FUNCTION update_last_modified()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_modified = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_jobs_last_modified
BEFORE UPDATE ON jobs
FOR EACH ROW
EXECUTE FUNCTION update_last_modified();

-- Grant permissions to ats_user
GRANT ALL PRIVILEGES ON DATABASE ats_optimizer TO ats_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ats_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ats_user;