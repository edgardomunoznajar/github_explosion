-- Step 4: Commit size distribution shift over time
-- AI-assisted developers tend to push larger, less frequent batches.
-- A shift in the commit size distribution post-2022 is an AI signal.

SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(QUARTER FROM created_at) AS quarter,
  COUNT(*) AS total_push_events,
  AVG(CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64)) AS avg_commits_per_push,
  APPROX_QUANTILES(
    CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64), 100
  )[OFFSET(25)] AS p25_commits_per_push,
  APPROX_QUANTILES(
    CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64), 100
  )[OFFSET(50)] AS median_commits_per_push,
  APPROX_QUANTILES(
    CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64), 100
  )[OFFSET(75)] AS p75_commits_per_push,
  APPROX_QUANTILES(
    CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64), 100
  )[OFFSET(95)] AS p95_commits_per_push,
  STDDEV(CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64)) AS stddev_commits_per_push
FROM `githubarchive.month.*`
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
GROUP BY year, quarter
ORDER BY year, quarter;


-- Variant: by language (top languages only)
-- GH Archive PushEvent doesn't include language directly,
-- but we can join on repo names with a separate language query.
-- For simplicity, this variant uses the repo table from GitHub's public dataset.

WITH push_data AS (
  SELECT
    EXTRACT(YEAR FROM created_at) AS year,
    EXTRACT(QUARTER FROM created_at) AS quarter,
    repo.name AS repo_name,
    CAST(JSON_EXTRACT_SCALAR(payload, '$.size') AS INT64) AS commits_per_push
  FROM `githubarchive.month.*`
  WHERE type = 'PushEvent'
    AND _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
),
repo_languages AS (
  SELECT
    repo_name,
    language.name AS language
  FROM `bigquery-public-data.github_repos.languages`,
  UNNEST(language) AS language
  WHERE language.name IN ('Python', 'JavaScript', 'TypeScript', 'Java', 'C++', 'C', 'Go', 'Rust')
  QUALIFY ROW_NUMBER() OVER (PARTITION BY repo_name ORDER BY language.bytes DESC) = 1
)
SELECT
  p.year,
  p.quarter,
  r.language,
  COUNT(*) AS total_pushes,
  AVG(p.commits_per_push) AS avg_commits_per_push,
  APPROX_QUANTILES(p.commits_per_push, 100)[OFFSET(50)] AS median_commits_per_push
FROM push_data p
INNER JOIN repo_languages r ON p.repo_name = r.repo_name
GROUP BY p.year, p.quarter, r.language
ORDER BY p.year, p.quarter, r.language;
