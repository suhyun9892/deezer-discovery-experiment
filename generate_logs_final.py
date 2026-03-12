"""
generate_logs.py
Deezer Context-Aware Recommendation — A/B Test Simulation

Pipeline: generate_logs.py -> GCP Cloud Storage -> BigQuery -> dbt -> Tableau

[Design assumptions]
- Revenue model : Direct subscription only (Freemium -> Premium). Partnership bundles excluded.
- LTV formula   : ARPU x Gross Margin / Monthly Churn Rate (industry standard)
- Primary OEC   : D+30 Retention Rate (common Netflix/Spotify style benchmark)
- Sample size   : 20,000 users (Control 10,000 / Treatment 10,000), 30-day cohort window
- Data sources  : Deezer FY2024 IR, Business of Apps 2024 Music App Benchmarks

[Recommendation Unit vs Consumption Unit - Important]
Following common analytics practice, recommendation exposure and content consumption
are modeled as separate units.

  Recommendation Unit:
    -> Playlist card exposure/click (card_title, context_id, section)
    -> Example: "Samba Avenue", "Context_Aware_Recommendation"

  Consumption Unit:
    -> Individual track playback after entering that playlist (play event)
    -> play_duration_sec: how many seconds the user listened to that track
    -> skip_flag: whether that track is treated as an early skip

  In practice:
      recommendation_click = playlist card click
      play                 = track playback inside that playlist
      play_duration_sec    = post-click track listening time
                             (track-level, not total playlist length)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# =============================================================================
#  0. Reproducibility
# =============================================================================
# Fix the seed so the simulation produces the same result on every run.
# This is important for portfolio review because the headline numbers should stay stable.
np.random.seed(42)


# =============================================================================
#  1. Simulation Config
# =============================================================================

# -- User volume and date window ------------------------------------------------
NUM_USERS    = 20_000
# The cohort starts on 2025-02-01 and COHORT_END is set to 2025-03-02.
# signup dates are sampled with randint(0, 29+1), so the actual last signup date is 2025-03-01.
# Users who sign up on the same day form the same cohort for D+N retention analysis.
COHORT_START = datetime(2025, 2, 1)
COHORT_END   = datetime(2025, 3, 2)
# Observation end date: set so even the latest signup can still be observed through D+30.
OBS_END      = datetime(2025, 4, 1)

# -- Countries ------------------------------------------------------------------
# FR is Deezer's home market, while DE and BR are major growth markets.
# The weights follow the market mix reflected in Deezer FY2024 IR.
COUNTRIES        = ['FR', 'DE', 'BR']
COUNTRY_WEIGHTS  = [0.40, 0.30, 0.30]

# Device mix by form factor (mobile-heavy).
# For a home-feed UI test, screen size and layout matter more than OS,
# so the simulation uses mobile / desktop / tablet instead of iOS / Android.
DEVICES        = ['mobile', 'desktop', 'tablet']
DEVICE_WEIGHTS = [0.70, 0.20, 0.10]


# =============================================================================
#  2. Revenue Parameters
# =============================================================================
# Source: Deezer pricing pages + FY2024 IR (Direct subscription only)
# ARPU is lower than list price (€11.99) because discounts and promos are assumed.
ARPU = {
    'FR': 10.99,   # EUR/month - Western Europe direct premium baseline
    'DE': 10.99,   # EUR/month - same pricing tier
    'BR':  5.99,   # EUR/month - localized emerging-market pricing
}

# Gross Margin: Deezer FY2024 Direct adjusted GM was 25.9% (Deezer FY2024 IR).
# Simplified conservatively to 25% for LTV calculation: ARPU * GROSS_MARGIN / MONTHLY_CHURN.
GROSS_MARGIN  = 0.25

# Monthly Churn Rate: 0.05 (5%)
# Deezer has not publicly disclosed churn figures.
# Proxy basis: Spotify CFO Paul Vogel (2021 investor day) reported 3.9% global average,
# down from 5.5% in 2017. Spotify's current ~2% (Antenna, June 2024) reflects
# 10+ years of algorithmic lock-in in mature markets — not applicable to Deezer.
# Deezer's subscriber base declined from 10.0M (2023) to 9.7M (2024) despite
# new partnership inflows (Deezer FY2024 IR), implying organic churn meaningfully
# above Spotify. 5% is applied as a conservative estimate for a mid-tier platform
# with high bundle trial dependency and limited algorithmic retention moat.
MONTHLY_CHURN = 0.05

# Trial Conversion Rate (free -> premium)
# Source: Business of Apps 2024 Music App Benchmarks (~3% median)
# Treatment can rise toward 6% with better engagement.
CONV_RATE_BASE = 0.03   # Control baseline
CONV_RATE_MAX  = 0.06   # Shared upper bound for conv_prob (both groups); treatment multiplier can push toward this ceiling


def calc_ltv(country: str) -> float:
    """
    LTV = ARPU * GROSS_MARGIN / MONTHLY_CHURN  (standard subscription LTV formula)

    Results:
      FR / DE : 10.99 * 0.25 / 0.05 = 54.95 EUR
      BR      :  5.99 * 0.25 / 0.05 = 29.95 EUR

    Used as reference for fact_user_performance.sql — keeping the formula here
    ensures SQL hard-coded values stay in sync with these parameters.
    """
    return round(ARPU[country] * GROSS_MARGIN / MONTHLY_CHURN, 2)


# =============================================================================
#  3. Weather Distributions
# =============================================================================
# Country-level seasonal weather distribution for the Feb-Mar cohort window.
# Weather affects context-card selection (Priority 2 and 3).
WEATHER_OPTIONS = ['Sunny', 'Cloudy', 'Rainy', 'Snowy']
WEATHER_PROBS = {
    'FR': [0.25, 0.35, 0.30, 0.10],   # Mild winter, frequent rain
    'DE': [0.20, 0.30, 0.25, 0.25],   # Colder winter, more snow
    'BR': [0.60, 0.20, 0.20, 0.00],   # Southern hemisphere summer / carnival season
}


# =============================================================================
#  4. Local Events
# =============================================================================
def is_local_event(country, date_obj):
    """
    Check whether a local event is active for the given country and date.

    Returns: (is_event: bool, event_name: str | None)

    Design principles:
    - Events are modeled as realistic windows, not just one-day spikes.
    - During event windows, event-based cards have the highest priority.
    - Treatment CTR receives an event bonus during those windows.
    """
    m, d = date_obj.month, date_obj.day

    # -- France: Nice Carnival --------------------------------------------------
    # Simulation window: Feb 12 to Mar 2
    # Includes the official event period plus a pre-event interest ramp.
    if country == 'FR' and ((m == 2 and d >= 12) or (m == 3 and d <= 2)):
        return True, 'Nice_Carnival'

    # -- Germany: Cologne Carnival ---------------------------------------------
    # Simulation window: Feb 20 to Mar 4
    # Includes a pre-event window so the cohort sees enough event exposure.
    if country == 'DE' and ((m == 2 and d >= 20) or (m == 3 and d <= 4)):
        return True, 'Cologne_Carnival'

    # -- Brazil: Rio Carnival ---------------------------------------------------
    # Simulation window: Feb 22 to Mar 4
    # Includes a short build-up period before the main parade.
    if country == 'BR' and ((m == 2 and d >= 22) or (m == 3 and d <= 4)):
        return True, 'Rio_Carnival'

    return False, None


# =============================================================================
#  5. Context Card Mapping
# =============================================================================
# Recommendation card mapping: (context_id, card_title, card_genre)
#
# Design principles:
# - context_id should stay simple because it is used for aggregation.
# - This experiment has one recommendation module, so all recommendation variants
#   roll up into the same context_id: 'Context_Aware_Recommendation'.
# - The reason a recommendation was shown is explained separately through
#   local_event / weather / event_hour.
CONTEXT_MAP = {
    # Event-driven cards
    'Nice_Carnival':    ('Context_Aware_Recommendation', 'Riviera Parade',     'French Pop/Dance'),
    'Cologne_Carnival': ('Context_Aware_Recommendation', 'Koeln Fest Energy',  'Schlager/Party Pop'),
    'Rio_Carnival':     ('Context_Aware_Recommendation', 'Samba Avenue',       'Samba/Axe'),
    # Weather-driven cards (Priority 2: strong weather / Priority 3: softer weather)
    'Rainy':          ('Context_Aware_Recommendation', 'Cozy Jazz for Rain',  'Jazz/Lo-fi'),
    'Snowy':          ('Context_Aware_Recommendation', 'Winter Warmth',       'Acoustic'),
    'Sunny':          ('Context_Aware_Recommendation', 'Driving Hits',        'Pop/Rock'),
    'Cloudy':         ('Context_Aware_Recommendation', 'Lo-fi for Focus',     'Lo-fi/Chill'),
    # Time-of-day fallback cards (Priority 4)
    'morning':        ('Context_Aware_Recommendation', 'Start Your Day',      'Upbeat Pop'),
    'afternoon':      ('Context_Aware_Recommendation', 'Lo-fi for Focus',     'Lo-fi/Chill'),
    'evening':        ('Context_Aware_Recommendation', 'Relax After Work',    'R&B/Soul'),
    'night':          ('Context_Aware_Recommendation', 'Deep Sleep Sounds',   'Ambient/Piano'),
}


def get_context_card(country, date_obj, weather, hour):
    """
    Select a context card according to the priority rules.
    Returns: (context_id, card_title, card_genre)

    Priority:
      1. Local event  - event cards always win on event days
      2. Strong weather - Rainy / Snowy always override
      3. Soft weather - Sunny / Cloudy apply only 50% of the time
      4. Time of day  - fallback when no stronger context applies
    """
    # Priority 1: local event
    has_event, event_name = is_local_event(country, date_obj)
    if has_event and event_name in CONTEXT_MAP:
        return CONTEXT_MAP[event_name]

    # Priority 2: strong weather (Rainy / Snowy) always overrides
    if weather in ('Rainy', 'Snowy'):
        return CONTEXT_MAP[weather]

    # Priority 3: soft weather (Sunny / Cloudy) applies only 50% of the time
    # This prevents the feed from feeling too repetitive on every sunny/cloudy day.
    if weather in ('Sunny', 'Cloudy') and np.random.random() < 0.5:
        return CONTEXT_MAP[weather]

    # Priority 4: time-of-day fallback
    if 5 <= hour < 12:
        return CONTEXT_MAP['morning']
    elif 12 <= hour < 18:
        return CONTEXT_MAP['afternoon']
    elif 18 <= hour < 22:
        return CONTEXT_MAP['evening']
    else:
        return CONTEXT_MAP['night']


# =============================================================================
#  6. Hour Distribution
# =============================================================================
# A weighted 24-hour listening curve based on realistic streaming behavior.
# Late night is low, commute windows and evening hours are higher.
_hour_weights = np.array([
    0.005, 0.003, 0.002, 0.002, 0.003, 0.010,  # 0-5   Late night / early morning
    0.025, 0.045, 0.055, 0.050, 0.045, 0.040,  # 6-11  Morning build
    0.060, 0.065, 0.060, 0.050, 0.045, 0.055,  # 12-17 Afternoon
    0.075, 0.080, 0.075, 0.060, 0.040, 0.020,  # 18-23 Evening peak
])
_hour_weights /= _hour_weights.sum()   # Normalize to sum to 1.0


# =============================================================================
#  7. Click-Through Rate Parameters
# =============================================================================
# Cannibalization setup:
# Recommendation CTR is higher in Treatment, while Recently Played CTR drops somewhat,
# creating a realistic traffic shift from the legacy module to the new module.
#
# Target:
# Cannibalization = (plays_RP_control - plays_RP_treatment) / plays_RP_control
#                 -> measures drop in RP section consumption, not just clicks
#                 -> target: 10-30% range
# Net Click Growth = (total_plays_treatment - total_plays_control) / total_plays_control
#                 -> measures whether total consumption increased despite cannibalization
#                 -> should stay positive
#
# Control: only Recently Played is shown, so only one CTR baseline is needed.
CTR_CONTROL_RP    = 0.20   # Control Recently Played CTR

# Treatment: CTR depends on which section is shown
CTR_TREATMENT_RP  = 0.17   # Lower RP CTR due to traffic shifting toward recommendations
CTR_TREATMENT_REC = 0.30   # Higher recommendation CTR for the context-aware module

CTR_EVENT_BONUS   = 0.05   # Event-period bonus: event cards are more attractive


# =============================================================================
#  8. Engagement Parameters
# =============================================================================

# Probability that a playlist-card click turns into an actual playback start.
# A user can still leave after clicking the card without starting the first track.
PLAY_PROB = 0.80

# Likes are explicit feedback, so they happen less often.
# Here, a like means the user liked the currently playing track inside the playlist.
# A like is only possible if that track was not skipped.
LIKE_PROB = 0.18

# Some users skip the first track after entering a recommended playlist.
# In this simulation, skip=True is represented by forcing playback duration to stay at 30s or less.
SKIP_PROB = 0.30

# Playback duration distribution (mean_sec, std_sec)
# play_duration_sec measures the individual track playback that happens after
# the user enters a playlist, not the total playlist listening time.
# Recommendation is the exposure unit (playlist card), while playback is the
# consumption unit (track-level listening), which matches common industry practice.
#
# recently_played: history-based entry -> familiar tracks -> longer listening
# recommendation : playlist exploration -> shorter first-track listening on average
PLAY_DURATION_DIST = {
    'recently_played': (180, 60),
    'recommendation':  (140, 80),
}


# =============================================================================
#  9. Satisfaction & Visit Probability
# =============================================================================
# Satisfaction is an internal user-state score capped between 0.0 and 5.0.
# Clicks, plays, and likes increase it. No click or a failed play decreases it.
#
# The cap is important:
# In the original version, satisfaction grew without a ceiling,
# forcing visit_prob to stay pinned at the maximum.
SAT_CAP      = 5.0
SAT_CLICK    = +0.5
SAT_PLAY     = +0.3
SAT_LIKE     = +0.2
SAT_NO_CLICK = -0.1
SAT_NO_PLAY  = -0.05

# visit_prob = base_visit + SAT_FACTOR * satisfaction - BOREDOM_FACTOR * boredom_streak
#
# - Before D+7: higher baseline because of post-signup exploration
# - After D+7 : lower steady-state baseline
# - Higher satisfaction increases return probability
# - Repeated non-visits reduce return probability
BASE_VISIT_D0_7 = 0.55
BASE_VISIT_D7P  = 0.30
SAT_FACTOR      = 0.06
BOREDOM_FACTOR  = 0.04
VISIT_MIN       = 0.05
VISIT_MAX       = 0.75


# =============================================================================
#  10. Churn Logic
# =============================================================================
# Voluntary churn is triggered when visit_prob stays below the churn threshold
# for CHURN_STREAK consecutive days.
#
# Churn is only evaluated after D+7, because low engagement in the first few days
# can still be normal during onboarding.
CHURN_THRESHOLD = 0.10
CHURN_STREAK    = 3


# =============================================================================
#  STEP 1: Generate Users
# =============================================================================
print('Generating users ...')
users = []
signup_range_days = (COHORT_END - COHORT_START).days

for i in range(NUM_USERS):
    # Country sampled by configured weights
    country = np.random.choice(COUNTRIES, p=COUNTRY_WEIGHTS)

    # Exact 50:50 assignment by index
    # This avoids sample-ratio mismatch caused by pure random assignment.
    user_group = 'control' if i < NUM_USERS // 2 else 'treatment'

    device = np.random.choice(DEVICES, p=DEVICE_WEIGHTS)

    # Signup date is sampled uniformly across the cohort window
    signup = COHORT_START + timedelta(days=int(np.random.randint(0, signup_range_days + 1)))

    users.append({
        'user_id':    f'u{10000 + i}',
        'country':    country,
        'user_group': user_group,
        'device':     device,
        'registration_date': signup,
    })

users_df = pd.DataFrame(users)
ctrl_n   = (users_df.user_group == 'control').sum()
trt_n    = (users_df.user_group == 'treatment').sum()
print(f'  {NUM_USERS:,} users  |  Control: {ctrl_n:,}  |  Treatment: {trt_n:,}')


# =============================================================================
#  STEP 2: Simulate Event Logs
# =============================================================================
print('Simulating events ...')
logs = []

for user in users:
    uid        = user['user_id']
    country    = user['country']
    user_group = user['user_group']
    signup     = user['registration_date']
    device     = user['device']

    # Per-user state variables
    satisfaction   = 0.0
    boredom_streak = 0
    low_prob_days  = 0
    tier           = 'free'
    monthly_rev    = 0.0
    churned        = False

    # Observe each user for up to 30 days after signup,
    # while also respecting the global observation end date.
    obs_days = min(30, (OBS_END - signup).days)

    # D+30 retention requires an actual day-30 record.
    # range(obs_days) would stop at 29, so +1 is required.
    for day_offset in range(obs_days + 1):
        if churned:
            break

        date_obj          = signup + timedelta(days=day_offset)
        days_since_signup = day_offset

        # Visit probability
        base  = BASE_VISIT_D0_7 if days_since_signup < 7 else BASE_VISIT_D7P
        vprob = (base
                 + SAT_FACTOR    * satisfaction
                 - BOREDOM_FACTOR * min(boredom_streak, 5))
        vprob = max(VISIT_MIN, min(vprob, VISIT_MAX))

        # Churn risk tracking
        if vprob < CHURN_THRESHOLD:
            low_prob_days += 1
        else:
            low_prob_days = 0

        # If churn risk stays low for long enough after D+7, log churn and stop.
        if low_prob_days >= CHURN_STREAK and days_since_signup >= 7:
            churned = True
            logs.append({
                'user_id':           uid,
                'event_date':        date_obj.strftime('%Y-%m-%d'),
                'days_since_signup': days_since_signup,
                'session_id':        None,
                'action':            'churn',
                'churn_type':        'voluntary',
                'country':           country,
                'user_group':        user_group,
                'device':            device,
                'registration_date': signup.strftime('%Y-%m-%d'),
                'subscription_tier': tier,
                'monthly_revenue':   monthly_rev,
                # Churn has no session-level or content-level metadata
                'event_hour':        None,
                'weather':           None,
                'local_event':       None,
                'context_id':        None,
                'card_title':        None,
                'card_genre':        None,
                'section':           None,
                'play_duration_sec': None,
                'skip_flag':         None,
                'tier_before':       None,
                'tier_after':        None,
                'revenue_change':    None,
            })
            break

        # Visit vs no-visit
        if np.random.random() > vprob:
            # Only count boredom after the first week; early non-visits are normal.
            if days_since_signup >= 7:
                boredom_streak += 1
            satisfaction = max(0.0, satisfaction + SAT_NO_CLICK)
            continue

        # Successful visit resets boredom streak
        boredom_streak = 0
        session_id = f'{uid}_d{days_since_signup}'

        # Context variables for the session
        event_hour = int(np.random.choice(range(24), p=_hour_weights))
        weather = np.random.choice(WEATHER_OPTIONS, p=WEATHER_PROBS[country])
        has_event, local_event = is_local_event(country, date_obj)
        context_id, card_title, card_genre = get_context_card(
            country, date_obj, weather, event_hour)

        # Section selection
        # Control always sees Recently Played.
        # Treatment sees a mix, with higher recommendation exposure during local events.
        if user_group == 'control':
            section = 'recently_played'
        else:
            p_rec     = 0.40 if has_event else 0.30
            section = 'recommendation' if np.random.random() < p_rec else 'recently_played'

        # Shared fields across all events in the same session
        base_log = {
            'user_id':           uid,
            'event_date':        date_obj.strftime('%Y-%m-%d'),
            'days_since_signup': days_since_signup,
            'session_id':        session_id,
            'event_hour':        event_hour,
            'weather':           weather,
            'local_event':       local_event,
            # recommendation uses a single aggregated context_id in this project
            'context_id':        context_id if section == 'recommendation' else 'Recently_Played',
            'card_title':        card_title  if section == 'recommendation' else 'Recently Played',
            'card_genre':        card_genre  if section == 'recommendation' else 'History',
            'section':           section,
            'country':           country,
            'user_group':        user_group,
            'device':            device,
            'registration_date': signup.strftime('%Y-%m-%d'),
            'subscription_tier': tier,
            'monthly_revenue':   monthly_rev,
            'play_duration_sec': None,
            'skip_flag':         None,
            'churn_type':        None,
            'tier_before':       None,
            'tier_after':        None,
            'revenue_change':    None,
        }

        # [Event 1] session_start
        # Used as the denominator for CTR.
        log = base_log.copy()
        log['action'] = 'session_start'
        logs.append(log)

        # Session-level CTR
        if user_group == 'control':
            ctr = CTR_CONTROL_RP
        else:
            ctr = CTR_TREATMENT_REC if section == 'recommendation' else CTR_TREATMENT_RP
            if has_event:
                ctr = min(ctr + CTR_EVENT_BONUS, 0.55)

        # Novelty effect: early CTR spike during onboarding (D+0 to D+6)
        if days_since_signup < 7:
            ctr = min(ctr * 1.15, 0.55)

        # [Event 2] section click
        # The click event name depends on which section was shown.
        if np.random.random() >= ctr:
            satisfaction = max(0.0, satisfaction + SAT_NO_CLICK)
            if days_since_signup >= 7:
                boredom_streak += 1
            continue

        log = base_log.copy()
        log['action'] = 'recommendation_click' if section == 'recommendation' else 'recently_played_click'
        logs.append(log)
        satisfaction = min(SAT_CAP, satisfaction + SAT_CLICK)

        # [Event 3] play
        # A playlist-card click does not always convert to first-track playback.
        if np.random.random() >= PLAY_PROB:
            satisfaction = max(0.0, satisfaction + SAT_NO_PLAY)
            continue

        # Early skip behavior for the track that starts after playlist entry
        skip = np.random.random() < SKIP_PROB

        # Sample track playback duration from the section-specific distribution
        # This is track-level duration, not total playlist length.
        dur_mean, dur_std = PLAY_DURATION_DIST[section]
        duration = max(5, int(np.random.normal(dur_mean, dur_std)))
        if skip:
            duration = min(duration, 30)

        log = base_log.copy()
        log['action']            = 'play'
        log['play_duration_sec'] = duration
        log['skip_flag']         = skip
        logs.append(log)

        satisfaction = min(SAT_CAP, satisfaction + (SAT_PLAY if not skip else SAT_NO_PLAY))

        # [Event 4] like
        # Like on the currently playing track inside the playlist.
        # Likes are only possible when the track was not skipped.
        if not skip and np.random.random() < LIKE_PROB:
            log = base_log.copy()
            log['action'] = 'like'
            logs.append(log)
            satisfaction = min(SAT_CAP, satisfaction + SAT_LIKE)

        # [Event 5] conversion (free -> premium)
        # Conversion is only possible after D+3.
        if tier == 'free' and days_since_signup >= 3:
            # Conversion probability rises with satisfaction
            sat_bonus = (satisfaction / SAT_CAP) * (CONV_RATE_MAX - CONV_RATE_BASE)
            conv_prob = CONV_RATE_BASE + sat_bonus

            # Treatment gets a lift because the recommendation experience is better
            if user_group == 'treatment':
                conv_prob = min(CONV_RATE_MAX, conv_prob * 1.2)

            if np.random.random() < conv_prob:
                tier_before = tier
                tier        = 'premium'
                monthly_rev = ARPU[country]

                log = base_log.copy()
                log['action']            = 'conversion'
                log['subscription_tier'] = 'premium'
                log['monthly_revenue']   = monthly_rev
                log['tier_before']       = tier_before
                log['tier_after']        = 'premium'
                log['revenue_change']    = monthly_rev
                logs.append(log)

                # Update the running state so later events reflect the premium tier
                base_log['subscription_tier'] = tier
                base_log['monthly_revenue']   = monthly_rev


# =============================================================================
#  STEP 3: Build DataFrame & Save
# =============================================================================
print('Building DataFrame ...')
logs_df = pd.DataFrame(logs)

# Keep a fixed column order to match the BigQuery schema.
# dbt staging will cast these fields downstream.
COLUMN_ORDER = [
    'user_id', 'event_date', 'days_since_signup', 'session_id', 'action',
    'event_hour', 'weather', 'local_event', 'context_id', 'card_title', 'card_genre',
    'section', 'country', 'user_group', 'device', 'registration_date',
    'subscription_tier', 'monthly_revenue',
    'play_duration_sec', 'skip_flag', 'churn_type',
    'tier_before', 'tier_after', 'revenue_change',
]
logs_df = logs_df[[c for c in COLUMN_ORDER if c in logs_df.columns]]


# =============================================================================
#  Sanity Check
# =============================================================================
# Quick validation after generation to see whether the simulation is behaving
# roughly in line with the design targets.
print('\n── Sanity Check ─────────────────────────────────────────')
print(f'  Total rows   : {len(logs_df):,}')
print(f'  Unique users : {logs_df.user_id.nunique():,}')

print(f'\n  Action breakdown:')
for action, cnt in logs_df.action.value_counts().items():
    print(f'    {action:<22} {cnt:>8,}')

sessions = logs_df[logs_df.action == 'session_start']
clicks = logs_df[logs_df.action.isin(['recently_played_click', 'recommendation_click'])]

# CTR target: Control ~20%, Treatment ~22-25%
if len(sessions) > 0:
    print(f'\n  CTR by group:')
    for grp in ['control', 'treatment']:
        v = sessions[sessions.user_group == grp]
        c = clicks[clicks.user_group == grp]
        ctr_val = len(c) / len(v) if len(v) > 0 else 0
        print(f'    {grp:<12} {ctr_val:.1%}')

# Trial Conversion target: Control ~3-4%, Treatment ~5-6%
conv_df = logs_df[logs_df.action == 'conversion']
if len(conv_df) > 0:
    print(f'\n  Trial Conversion Rate:')
    for grp in ['control', 'treatment']:
        n_conv  = conv_df[conv_df.user_group == grp].user_id.nunique()
        n_total = NUM_USERS // 2
        print(f'    {grp:<12} {n_conv:,} / {n_total:,}  ({n_conv/n_total:.1%})')

churns = logs_df[logs_df.action == 'churn']
print(f'\n  Churn events : {len(churns):,}')

# Cannibalization & Net Click Growth
# Cannibalization = drop in RP section plays (Spotify standard: plays over clicks)
#   = (plays_RP_control - plays_RP_treatment) / plays_RP_control
#
# Net Click Growth = increase in total plays across all sections
#   = (total_plays_treatment - total_plays_control) / total_plays_control
plays_df = logs_df[logs_df.action == 'play']

ctrl_rp_plays  = plays_df[(plays_df.user_group == 'control')   & (plays_df.section == 'recently_played')]
trt_rp_plays   = plays_df[(plays_df.user_group == 'treatment') & (plays_df.section == 'recently_played')]
ctrl_all_plays = plays_df[plays_df.user_group == 'control']
trt_all_plays  = plays_df[plays_df.user_group == 'treatment']

if len(ctrl_rp_plays) > 0:
    cannib     = (len(ctrl_rp_plays) - len(trt_rp_plays)) / len(ctrl_rp_plays)
    net_growth = (len(trt_all_plays) - len(ctrl_all_plays)) / len(ctrl_all_plays)

    print(f'\n  Cannibalization (RP plays drop): {cannib:.1%}  (target: 10-35%)')
    print(f'  Net Click Growth (total plays):  {net_growth:+.1%}  (should be positive)')

print('─────────────────────────────────────────────────────────\n')

# Save CSV
# This file can be uploaded to GCS and connected to BigQuery.
out_path = 'music_app_logs_final.csv'
logs_df.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f"Saved -> '{out_path}'")
print(f'Shape  : {logs_df.shape[0]:,} rows x {logs_df.shape[1]} columns')
