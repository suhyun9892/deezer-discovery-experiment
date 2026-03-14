{{
    config(
        materialized = 'table'
    )
}}

/*
    fact_waterfall
    ─────────────────────────────────────────────────────────────────────────
    grain           : 3 rows (one per waterfall step)
    role            : play volume shift for cannibalization waterfall chart
    upstream        : fact_user_summary
    downstream      : Tableau - Trade-off & Guardrail Analysis
*/

WITH
ctrl_rp AS (
    SELECT SUM(total_rp_clicks) AS plays
    FROM {{ ref('fact_user_summary') }}
    WHERE user_group = 'control'
),
trt_rp AS (
    SELECT SUM(total_rp_clicks) AS plays
    FROM {{ ref('fact_user_summary') }}
    WHERE user_group = 'treatment'
),
trt_rec AS (
    SELECT ROUND(SUM(overall_ctr * total_sessions)) AS plays
    FROM {{ ref('fact_user_summary') }}
    WHERE user_group = 'treatment'
)

SELECT
    '1. Control RP'             AS step,
    'control'                   AS user_group,
    'recently_played'           AS section,
    ctrl_rp.plays               AS total_plays,
    0                           AS start,
    'Baseline'                  AS color
FROM ctrl_rp, trt_rp, trt_rec

UNION ALL

SELECT
    '2. RP Drop (Cannibalized)',
    'treatment',
    'recently_played',
    trt_rp.plays - ctrl_rp.plays,
    ctrl_rp.plays,
    'Negative'
FROM ctrl_rp, trt_rp, trt_rec

UNION ALL

SELECT
    '3. Rec Add (New)',
    'treatment',
    'recommendation',
    trt_rec.plays,
    ctrl_rp.plays + (trt_rp.plays - ctrl_rp.plays),
    'Positive'
FROM ctrl_rp, trt_rp, trt_rec