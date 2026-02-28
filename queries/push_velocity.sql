-- Step 1: Per-developer push velocity time series
-- Normalises total pushes by unique pushers to isolate
-- per-developer velocity changes from population growth.
--
-- Dataset: githubarchive.month.*
-- Free tier: 1TB/month query processing
-- Expected output: ~60 rows (monthly from 2020-01 to 2025-08)

SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(MONTH FROM created_at) AS month,
  COUNT(*) AS total_pushes,
  COUNT(DISTINCT actor.login) AS unique_pushers,
  SAFE_DIVIDE(COUNT(*), COUNT(DISTINCT actor.login)) AS pushes_per_dev
FROM `githubarchive.month.*`
WHERE _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
  AND type = 'PushEvent'
GROUP BY year, month
ORDER BY year, month;


-- Variant: breakdown by repo size (solo vs org)
-- Solo repos = repos with <= 2 distinct pushers that month
-- This helps isolate "vibe coder" signal from enterprise growth

WITH repo_pushers AS (
  SELECT
    EXTRACT(YEAR FROM created_at) AS year,
    EXTRACT(MONTH FROM created_at) AS month,
    repo.name AS repo_name,
    COUNT(*) AS repo_pushes,
    COUNT(DISTINCT actor.login) AS repo_unique_pushers
  FROM `githubarchive.month.*`
  WHERE _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
    AND type = 'PushEvent'
  GROUP BY year, month, repo_name
),
classified AS (
  SELECT
    year,
    month,
    repo_name,
    repo_pushes,
    repo_unique_pushers,
    CASE
      WHEN repo_unique_pushers <= 2 THEN 'solo_or_pair'
      WHEN repo_unique_pushers <= 10 THEN 'small_team'
      ELSE 'large_org'
    END AS repo_class
  FROM repo_pushers
)
SELECT
  year,
  month,
  repo_class,
  SUM(repo_pushes) AS total_pushes,
  COUNT(DISTINCT repo_name) AS repo_count,
  SAFE_DIVIDE(SUM(repo_pushes), COUNT(DISTINCT repo_name)) AS pushes_per_repo
FROM classified
GROUP BY year, month, repo_class
ORDER BY year, month, repo_class;
