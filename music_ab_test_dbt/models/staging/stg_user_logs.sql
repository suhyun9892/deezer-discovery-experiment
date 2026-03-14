{{
    config(
        materialized = 'view'
    )
}}

/*
    stg_user_logs
    ─────────────────────────────────────────────────────────────────────────
    role            : raw log's type casting & organizing columns
                    no calculation (LTV, Retention, Cannibalization etc)
    principle       : raw = fact / staging - cleaning / mart - calculation
    original source : source('raw_data', 'music_app_logs')
                    = music-db-project-485112.side_project_logs.music_app_logs
    downstream      : fact_cohort_retention, fact_user_performance, fact_discovery_journey
*/

WITH source AS (
    SELECT *
    FROM {{ source('raw_data', 'music_app_user_logs') }}
),

staged AS (

    SELECT
        -- ── users ─────────────────────────────────────────────────────
        user_id,
        user_group,                                     -- control / treatment
        country,                                        -- FR / DE / BR
        device,                                         -- mobile / desktop / tablet

        -- ── date & session ───────────────────────────────────────────────────
        CAST(event_date AS DATE)            AS event_date,
        CAST(registration_date AS DATE)     AS registration_date,
        CAST(days_since_signup AS INT64)    AS days_since_signup,
        session_id,                                     -- e.g. u10001_d7, churn = NULL

        -- ── event ────────────────────────────────────────────────────────
        action,
        -- actions:
        --   session_start, recently_played_click, recommendation_click,
        --   play, like, conversion, churn
        CAST(event_hour AS INT64)           AS event_hour,   -- churn =  NULL

        -- ── context ────────────────────────────────────────────────
        weather,                                        -- Sunny/Cloudy/Rainy/Snowy. churn은 NULL
        local_event,                                    -- local event name. no context = NULL
        context_id,                                     -- recommendation context identifier. churn =  NULL
        card_title,                                     -- card title. churn = NULL
        card_genre,                                     -- card genre. churn = NULL
        section,                                        -- recently_played / recommendation. churn = NULL

        -- ── subscription & revenue ───────────────────────────────────────────────────
        subscription_tier,                              -- free / premium
        CAST(monthly_revenue AS FLOAT64)    AS monthly_revenue,

        -- ── play event only ─────────────────────────────────────────
        CAST(play_duration_sec AS INT64)    AS play_duration_sec,
        CAST(skip_flag AS BOOL)             AS skip_flag,

        -- ── churn event only ────────────────────────────────────────
        churn_type,                                     -- voluntary. churn

        -- ── conversion event only ──────────────────────────────────
        tier_before,                                    -- before conversion (free)
        tier_after,                                     -- after conversion (premium)
        CAST(revenue_change AS FLOAT64)     AS revenue_change   -- monthly revenue change because of conversion

    FROM source

)

SELECT * FROM staged