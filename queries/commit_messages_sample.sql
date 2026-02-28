-- Step 3 (data extraction): Sample commit messages for NLP analysis
-- Pull ~500k commit messages per quarter for embedding and classification.
-- GH Archive PushEvent payloads include commit messages in payload.commits[].message

-- Pre-AI sample (2021 Q1-Q4)
SELECT
  created_at,
  actor.login AS author,
  repo.name AS repo_name,
  JSON_EXTRACT_SCALAR(commit, '$.message') AS commit_message,
  JSON_EXTRACT_SCALAR(commit, '$.sha') AS commit_sha,
  'pre_ai' AS era
FROM `githubarchive.month.*`,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '2021_01' AND '2021_12'
  AND RAND() < 0.001  -- ~0.1% sample rate, adjust as needed
LIMIT 500000;


-- Post-AI sample (2024 Q1-Q4)
SELECT
  created_at,
  actor.login AS author,
  repo.name AS repo_name,
  JSON_EXTRACT_SCALAR(commit, '$.message') AS commit_message,
  JSON_EXTRACT_SCALAR(commit, '$.sha') AS commit_sha,
  'post_ai' AS era
FROM `githubarchive.month.*`,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '2024_01' AND '2024_12'
  AND RAND() < 0.001
LIMIT 500000;


-- Commit message length distribution over time (lightweight alternative)
SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(QUARTER FROM created_at) AS quarter,
  COUNT(*) AS total_commits,
  AVG(LENGTH(JSON_EXTRACT_SCALAR(commit, '$.message'))) AS avg_message_length,
  APPROX_QUANTILES(
    LENGTH(JSON_EXTRACT_SCALAR(commit, '$.message')), 100
  )[OFFSET(50)] AS median_message_length,
  COUNTIF(
    REGEXP_CONTAINS(
      JSON_EXTRACT_SCALAR(commit, '$.message'),
      r'^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.+\))?:'
    )
  ) AS conventional_commit_count,
  SAFE_DIVIDE(
    COUNTIF(
      REGEXP_CONTAINS(
        JSON_EXTRACT_SCALAR(commit, '$.message'),
        r'^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.+\))?:'
      )
    ),
    COUNT(*)
  ) AS conventional_commit_ratio
FROM `githubarchive.month.*`,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
GROUP BY year, quarter
ORDER BY year, quarter;


-- LLM SDK import detection
-- Count repos importing common LLM libraries over time
SELECT
  EXTRACT(YEAR FROM created_at) AS year,
  EXTRACT(QUARTER FROM created_at) AS quarter,
  COUNT(DISTINCT repo.name) AS repos_with_llm_commits,
  COUNT(*) AS total_llm_related_pushes
FROM `githubarchive.month.*`,
UNNEST(JSON_EXTRACT_ARRAY(payload, '$.commits')) AS commit
WHERE type = 'PushEvent'
  AND _TABLE_SUFFIX BETWEEN '2020_01' AND '2025_08'
  AND REGEXP_CONTAINS(
    LOWER(JSON_EXTRACT_SCALAR(commit, '$.message')),
    r'(openai|langchain|llama|anthropic|copilot|gpt|chatgpt|claude|gemini|ollama|huggingface|transformers)'
  )
GROUP BY year, quarter
ORDER BY year, quarter;
