{{
    config(
        materialized = 'table'
    )
}}

/*
    fact_user_summary
    ─────────────────────────────────────────────────────────────────────────
    grain           : user_id (1 row per user, ever)
    role            : per-user lifetime metrics & experiment outcome flags
    upstream        : stg_user_logs
    downstream      : Tableau - Overview KPI, Discovery Journey, LTV Simulator
*/
WITH stg_user_logs AS (
    SELECT * FROM {{ ref('stg_user_logs') }}
),
-- ── STEP 1: user profile ──────────────────────────────────────────────────
-- base table that guarantees one row per user
-- user_id always has the same group/country/device, so ANY_VALUE picks a representative
user_profile AS (

    SELECT
        user_id,
        ANY_VALUE(user_group)   AS user_group,
        ANY_VALUE(country)      AS country,
        ANY_VALUE(device)       AS device
    FROM stg_user_logs
    GROUP BY user_id

),

-- ── STEP 2: session & click aggregation ──────────────────────────────────
-- total sessions, recommendation clicks, and recently-played clicks over the full window
-- CTR = recommendation clicks / total sessions

session_stats AS (

    SELECT
        user_id,
        COUNTIF(action = 'session_start')           AS total_sessions,
        COUNTIF(action = 'recommendation_click')    AS total_rec_clicks,
        COUNTIF(action = 'recently_played_click')   AS total_rp_clicks
    FROM stg_user_logs
    GROUP BY user_id

),

-- ── STEP 3: play aggregation ─────────────────────────────────────────────
-- average play duration and skip rate across the full observation window
-- SAFE_DIVIDE: returns NULL instead of error when denominator is 0

play_stats AS (

    SELECT
        user_id,
        AVG(play_duration_sec)                              AS avg_play_duration_sec,
        SAFE_DIVIDE(
            COUNTIF(skip_flag = TRUE),
            COUNTIF(action = 'play')
        )                                                   AS skip_rate,

        -- section-level play duration for cannibalization measurement
        -- cannibalization = drop in RP stream share, not CTR drop
        AVG(CASE WHEN section = 'recently_played'
                 THEN play_duration_sec END)                AS avg_play_duration_rp,
        AVG(CASE WHEN section = 'recommendation'
                 THEN play_duration_sec END)                AS avg_play_duration_rec

    FROM stg_user_logs
    WHERE action = 'play'
    GROUP BY user_id

),

-- ── STEP 4: conversion ───────────────────────────────────────────────────
-- conversion flag + day of first conversion (days_since_signup)
-- users who never converted: converted=0, conversion_day=NULL

conversion AS (

    SELECT
        user_id,
        MAX(CASE WHEN action = 'conversion' THEN 1 ELSE 0 END)     AS converted,
        MIN(CASE WHEN action = 'conversion' THEN days_since_signup END) AS conversion_day
        -- MIN: use the first conversion day if multiple conversion events exist
    FROM stg_user_logs
    GROUP BY user_id

),

-- ── STEP 5: retention flags ──────────────────────────────────────────────
-- retained if user had a session_start on exactly day 7 or day 30

retention AS (

    SELECT
        user_id,
        MAX(CASE WHEN days_since_signup = 7  AND action = 'session_start' THEN 1 ELSE 0 END) AS retained_d7,
        MAX(CASE WHEN days_since_signup = 30 AND action = 'session_start' THEN 1 ELSE 0 END) AS retained_d30
    FROM stg_user_logs
    GROUP BY user_id

),

-- ── STEP 6: LTV calculation ──────────────────────────────────────────────
-- LTV = ARPU × Gross Margin / Monthly Churn Rate
-- ARPU by country: FR/DE = 10.99, BR = 5.99
-- Gross Margin = 0.25 (Deezer FY2024)
-- Monthly Churn = 0.05 (Spotify proxy)
--
-- LTV is only assigned to converted users; non-converted users get 0
-- blended_ltv = average LTV within user_group × country partition
--               used as the baseline value for the Tableau LTV Simulator slider

ltv AS (

    SELECT
        p.user_id,
        CASE
            WHEN c.converted = 1 AND p.country IN ('FR', 'DE')
                THEN ROUND(10.99 * 0.25 / 0.05, 2)   -- 54.95
            WHEN c.converted = 1 AND p.country = 'BR'
                THEN ROUND(5.99 * 0.25 / 0.05, 2)    -- 29.95
            ELSE 0
        END AS ltv

    FROM user_profile p
    LEFT JOIN conversion c USING (user_id)

),

-- blended_ltv: average LTV within the same group × country bucket
-- reflects group-level expected LTV accounting for conversion rate differences
-- e.g. average LTV of converted users in treatment × FR

blended AS (

    SELECT
        p.user_id,
        AVG(l.ltv) OVER (
            PARTITION BY p.user_group, p.country
        ) AS blended_ltv
        -- OVER: window function — computes aggregate without collapsing rows
        -- PARTITION BY user_group, country: average is scoped to each group × country bucket
    FROM user_profile p
    LEFT JOIN ltv l USING (user_id)

)

-- ── FINAL: join all CTEs ─────────────────────────────────────────────────
-- user_profile is the anchor (LEFT base); all others join on user_id
-- LEFT JOIN: preserves users with no sessions or plays (NULL fills in)

SELECT
    p.user_id,
    p.user_group,
    p.country,
    p.device,

    -- conversion
    c.converted,
    c.conversion_day,

    -- LTV
    l.ltv,
    b.blended_ltv,

    -- retention
    r.retained_d7,
    r.retained_d30,

    -- Session / CTR
    s.total_sessions,
    SAFE_DIVIDE(s.total_rec_clicks, s.total_sessions)   AS overall_ctr,
    -- overall_ctr = total recommendation clicks / total sessions over full window
    s.total_rp_clicks,

    -- Play
    pl.avg_play_duration_sec,
    pl.skip_rate,
    pl.avg_play_duration_rp,
    pl.avg_play_duration_rec

FROM user_profile     p
LEFT JOIN session_stats  s  USING (user_id)
LEFT JOIN play_stats     pl USING (user_id)
LEFT JOIN conversion     c  USING (user_id)
LEFT JOIN retention      r  USING (user_id)
LEFT JOIN ltv            l  USING (user_id)
LEFT JOIN blended        b  USING (user_id)