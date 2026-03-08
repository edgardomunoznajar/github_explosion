-- Claude Commit Detection Queries for GH Archive (BigQuery)
--
-- COST NOTE: Each month of PushEvents is ~200 GB due to the payload column.
-- The free tier is 1 TB/month. Run queries on 1-5 months at a time.
-- Use the Python wrapper to iterate month-by-month if needed.
--
-- Detection signals:
--   1. Co-Authored-By: Claude ... @anthropic.com
--   2. "Generated with [Claude Code]"
--   3. Author email noreply@anthropic.com


-- ============================================================
-- Query 1: Claude commits for a single month (parameterise _TABLE_SUFFIX)
-- Cost: ~200 GB per month scanned
-- The Python wrapper iterates over months to build the full time series.
-- ============================================================

WITH claude_pushes AS (
  SELECT
    created_at,
    actor.login,
    repo.name AS repo_name,
    payload
  FROM `githubarchive.month.MONTH_PLACEHOLDER`
  WHERE type = 'PushEvent'
    AND (
      STRPOS(payload, 'anthropic.com') > 0
      OR STRPOS(payload, 'Claude Code') > 0
    )
)
SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(MONTH FROM created_at) AS month,
  COUNT(*) AS claude_commits,
  COUNT(DISTINCT repo_name) AS distinct_repos,
  COUNT(DISTINCT login) AS distinct_developers
FROM claude_pushes,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE
  REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com'
  )
  OR REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'Generated with \[?Claude Code\]?'
  )
  OR JSON_EXTRACT_SCALAR(commit, '$.author.email') = 'noreply@anthropic.com'
GROUP BY year, month;


-- ============================================================
-- Query 2: Top repos for a single month
-- ============================================================

WITH claude_pushes AS (
  SELECT created_at, actor.login, repo.name AS repo_name, payload
  FROM `githubarchive.month.MONTH_PLACEHOLDER`
  WHERE type = 'PushEvent'
    AND (
      STRPOS(payload, 'anthropic.com') > 0
      OR STRPOS(payload, 'Claude Code') > 0
    )
)
SELECT
  repo_name,
  COUNT(*) AS claude_commits,
  COUNT(DISTINCT login) AS distinct_developers,
  MIN(created_at) AS first_claude_commit,
  MAX(created_at) AS last_claude_commit
FROM claude_pushes,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE
  REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com'
  )
  OR REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'Generated with \[?Claude Code\]?'
  )
  OR JSON_EXTRACT_SCALAR(commit, '$.author.email') = 'noreply@anthropic.com'
GROUP BY repo_name
ORDER BY claude_commits DESC
LIMIT 500;


-- ============================================================
-- Query 3: Model variant breakdown for a single month
-- ============================================================

WITH claude_pushes AS (
  SELECT created_at, repo.name AS repo_name, payload
  FROM `githubarchive.month.MONTH_PLACEHOLDER`
  WHERE type = 'PushEvent'
    AND (
      STRPOS(payload, 'anthropic.com') > 0
      OR STRPOS(payload, 'Claude Code') > 0
    )
),
claude_commits AS (
  SELECT
    created_at,
    repo_name,
    JSON_EXTRACT_SCALAR(commit, '$.message') AS message,
    JSON_EXTRACT_SCALAR(commit, '$.author.email') AS author_email
  FROM claude_pushes,
  UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
  WHERE
    REGEXP_CONTAINS(
      JSON_EXTRACT_SCALAR(commit, '$.message'),
      r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com'
    )
    OR REGEXP_CONTAINS(
      JSON_EXTRACT_SCALAR(commit, '$.message'),
      r'Generated with \[?Claude Code\]?'
    )
    OR JSON_EXTRACT_SCALAR(commit, '$.author.email') = 'noreply@anthropic.com'
)
SELECT
  CASE
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\s+opus') THEN 'opus'
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\s+sonnet') THEN 'sonnet'
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\s+haiku') THEN 'haiku'
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\s+code') THEN 'claude_code'
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com') THEN 'claude_unspecified'
    WHEN REGEXP_CONTAINS(message, r'Generated with \[?Claude Code\]?') THEN 'body_marker_only'
    ELSE 'author_email_only'
  END AS attribution_type,
  COUNT(*) AS commit_count,
  COUNT(DISTINCT repo_name) AS distinct_repos
FROM claude_commits
GROUP BY attribution_type
ORDER BY commit_count DESC;


-- ============================================================
-- Query 4: Sample Claude commits with full metadata (single month)
-- ============================================================

WITH claude_pushes AS (
  SELECT created_at, actor.login, repo.name AS repo_name, payload
  FROM `githubarchive.month.MONTH_PLACEHOLDER`
  WHERE type = 'PushEvent'
    AND (
      STRPOS(payload, 'anthropic.com') > 0
      OR STRPOS(payload, 'Claude Code') > 0
    )
)
SELECT
  created_at,
  login AS developer,
  repo_name,
  JSON_EXTRACT_SCALAR(commit, '$.sha') AS commit_sha,
  JSON_EXTRACT_SCALAR(commit, '$.message') AS commit_message,
  JSON_EXTRACT_SCALAR(commit, '$.author.name') AS author_name,
  JSON_EXTRACT_SCALAR(commit, '$.author.email') AS author_email
FROM claude_pushes,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE
  REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com'
  )
  OR REGEXP_CONTAINS(
    JSON_EXTRACT_SCALAR(commit, '$.message'),
    r'Generated with \[?Claude Code\]?'
  )
  OR JSON_EXTRACT_SCALAR(commit, '$.author.email') = 'noreply@anthropic.com'
ORDER BY created_at DESC
LIMIT 1000;


-- ============================================================
-- Query 6: All AI tools in a single scan (Claude, Aider, Devin, OpenAI Codex)
-- Cost: ~392 GB per month (same as a single-tool query — one scan catches all)
-- ============================================================

WITH ai_pushes AS (
  SELECT
    created_at,
    actor.login,
    repo.name AS repo_name,
    payload
  FROM `githubarchive.month.MONTH_PLACEHOLDER`
  WHERE type = 'PushEvent'
    AND (
      STRPOS(payload, 'anthropic.com') > 0
      OR STRPOS(payload, 'Claude Code') > 0
      OR STRPOS(payload, 'aider') > 0
      OR STRPOS(payload, 'openai.com') > 0
      OR STRPOS(payload, 'devin-ai') > 0
      OR STRPOS(payload, 'Codex CLI') > 0
    )
),
ai_commits AS (
  SELECT
    created_at,
    login,
    repo_name,
    JSON_EXTRACT_SCALAR(commit, '$.message') AS message,
    JSON_EXTRACT_SCALAR(commit, '$.author.name') AS author_name,
    JSON_EXTRACT_SCALAR(commit, '$.author.email') AS author_email
  FROM ai_pushes,
  UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
)
SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(MONTH FROM created_at) AS month,
  CASE
    -- Claude Code
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com')
      OR REGEXP_CONTAINS(message, r'Generated with \[?Claude Code\]?')
      OR author_email = 'noreply@anthropic.com'
      THEN 'claude'
    -- Aider
    WHEN REGEXP_CONTAINS(message, r'(?i)^aider:')
      OR REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*aider\b')
      THEN 'aider'
    -- OpenAI Codex CLI
    WHEN REGEXP_CONTAINS(message, r'(?i)co-authored-by:.*@openai\.com')
      OR REGEXP_CONTAINS(message, r'(?i)generated by.*codex\s*cli')
      OR author_email = 'noreply@openai.com'
      THEN 'openai_codex'
    -- Devin
    WHEN login = 'devin-ai-integration'
      OR REGEXP_CONTAINS(COALESCE(author_name, ''), r'(?i)devin-ai')
      OR REGEXP_CONTAINS(COALESCE(author_email, ''), r'(?i)devin-ai')
      THEN 'devin'
    ELSE NULL
  END AS tool,
  COUNT(*) AS commits,
  COUNT(DISTINCT repo_name) AS distinct_repos,
  COUNT(DISTINCT login) AS distinct_developers
FROM ai_commits
WHERE
  -- At least one signal must match
  REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*claude\b.*@anthropic\.com')
  OR REGEXP_CONTAINS(message, r'Generated with \[?Claude Code\]?')
  OR author_email = 'noreply@anthropic.com'
  OR REGEXP_CONTAINS(message, r'(?i)^aider:')
  OR REGEXP_CONTAINS(message, r'(?i)co-authored-by:\s*aider\b')
  OR REGEXP_CONTAINS(message, r'(?i)co-authored-by:.*@openai\.com')
  OR REGEXP_CONTAINS(message, r'(?i)generated by.*codex\s*cli')
  OR author_email = 'noreply@openai.com'
  OR login = 'devin-ai-integration'
  OR REGEXP_CONTAINS(COALESCE(author_name, ''), r'(?i)devin-ai')
  OR REGEXP_CONTAINS(COALESCE(author_email, ''), r'(?i)devin-ai')
GROUP BY year, month, tool
HAVING tool IS NOT NULL
ORDER BY year, month, commits DESC;


-- ============================================================
-- Query 5: Total push count per month (denominator, no payload scan)
-- Cost: ~4 GB per year — very cheap
-- ============================================================

SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(MONTH FROM created_at) AS month,
  COUNT(*) AS total_push_events,
  COUNT(DISTINCT actor.login) AS unique_pushers,
  COUNT(DISTINCT repo.name) AS unique_repos
FROM `githubarchive.month.*`
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '202401' AND '202602'
GROUP BY year, month
ORDER BY year, month;
