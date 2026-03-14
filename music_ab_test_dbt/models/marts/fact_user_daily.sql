{{
    config(
        materialized = 'table'
    )
}}

/*
    fact_user_daily
    ─────────────────────────────────────────────────────────────────────────
    grain           : user_id × days_since_signup (1 row per user per day)
    role            : daily behaviour metrics per user
                      time-series grain for retention curves & novelty effect
    upstream        : stg_user_logs
    downstream      : Tableau - Cohort Retention view, Novelty Effect view
*/
WITH stg_user_logs AS (
    SELECT * FROM {{ ref('stg_user_logs') }}
),

daily_events AS (

    SELECT
        -- ── identity ──────────────────────────────────────────────────────
        user_id,
        user_group,
        country,
        device,

        -- ── time ──────────────────────────────────────────────────────────
        days_since_signup,
        MIN(event_date)                                     AS event_date,
        -- representative date for this day: earliest event on the same days_since_signup

        -- ── session ───────────────────────────────────────────────────────
        MAX(CASE WHEN action = 'session_start'          THEN 1 ELSE 0 END)  AS had_session,
        -- 1 if at least one session_start occurred on this day, else 0

        -- ── clicks ────────────────────────────────────────────────────────
        MAX(CASE WHEN action = 'recommendation_click'   THEN 1 ELSE 0 END)  AS had_rec_click,
        MAX(CASE WHEN action = 'recently_played_click'  THEN 1 ELSE 0 END)  AS had_rp_click,
        -- 0/1 flag: whether each click type occurred at least once on this day

        -- ── play ──────────────────────────────────────────────────────────
        COUNTIF(action = 'play')                            AS play_count,
        -- number of tracks played on this day

        AVG(CASE WHEN action = 'play'
                 THEN play_duration_sec END)                AS avg_play_duration_sec,
        -- average play duration in seconds on this day
        -- non-play rows return NULL (no ELSE), so AVG automatically excludes them

        MAX(CASE WHEN action = 'play'
                      AND skip_flag = TRUE  THEN 1 ELSE 0 END)  AS had_skip,
        -- 1 if any play event on this day was skipped, else 0

        -- ── conversion & churn ────────────────────────────────────────────
        MAX(CASE WHEN action = 'conversion'             THEN 1 ELSE 0 END)  AS had_conversion,
        MAX(CASE WHEN action = 'churn'                  THEN 1 ELSE 0 END)  AS had_churn
        -- 0/1 flag: whether conversion or churn occurred on this day

    FROM stg_user_logs

    GROUP BY
        user_id,
        user_group,
        country,
        device,
        days_since_signup
    -- collapse all events within a user × day into a single row

)

SELECT * FROM daily_events