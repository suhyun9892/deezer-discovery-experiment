import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta

# 0. Configuration
np.random.seed(42)
random.seed(42)

fake = Faker()
NUM_USERS = 1000
START_DATE = datetime(2025, 2, 1)
END_DATE = datetime(2025, 7, 31)
PLATFORMS = ['iOS', 'Android']
COUNTRIES = ['FR', 'BR']
GROUPS = ['Control', 'Treatment']

# 1. Triger logic function
def get_context_card(country, date_obj, weather, hour):

    # Priority 1: Special Events
    if date_obj.month == 2 and date_obj.day == 14:
         return "Valentine_Day", "Romantic Vibes", "R&B/Ballad"
    
    if country == 'BR' and ((date_obj.month == 2 and date_obj.day >= 28) or (date_obj.month == 3 and date_obj.day <= 5)):
        return "Rio_Carnival_Live", "Samba Energy", "Samba/Pagode"
    
    if country == 'FR' and date_obj.month == 7 and date_obj.day == 14:
        return "Bastille_Day_Vibes", "Parisian Night", "French Electro/Pop"
    
    if country == 'FR' and date_obj.month == 6 and date_obj.day == 21:
        return "Music_Festival_Day", "Street Music Party", "Live/Acoustic"
    
    # Priority 2: Weather
    if weather == 'Rainy':
        return "Rainy_Day_Jazz", "Cozy Jazz for Rain", "Jazz/Lo-fi"
    elif weather == 'Sunny':
        return "Sunny_Drive", "Driving Hits", "Pop/Rock"
    elif weather == 'Snowy':
        return "Snowy_Cabin", "Winter Warmth", "Acoustic"
    elif weather == 'Cloudy':
        return "Windy_classic", "Calm music", "Peaceful R&B"
    
    # Priority 3: Daily Routine
    if 5 <= hour < 12:
        return "Morning_Boost", "Start your day", "Upbeat Pop"
    elif 12 <= hour < 18:
        return "Afternoon_Focus", "Lo-fi for Focus", "Energetic Pop"
    elif 18 <= hour < 22:
        return "Evening_Chill", "Relax after work", "R&B/Soul"
    else:
        return "Night_Sleep", "Deep Sleep Sounds", "Ambient/Piano"

# 2. User Generation
users = []
print('Generating users ...')

for i in range(NUM_USERS):
    user_id = i+10000
    country = np.random.choice(COUNTRIES, p=[0.5, 0.5]) # FR 50%, BR 50%
    group = np.random.choice(GROUPS, p=[0.5, 0.5]) # A/B Test Group

    days_offset = np.random.randint(0,150)
    signup_date = START_DATE + timedelta(days=days_offset)

    users.append({
        'user_id': user_id,
        'country': country,
        'group': group,
        'signup_date': signup_date,
        'platform': np.random.choice(PLATFORMS)
    })
users_df = pd.DataFrame(users)
print(f'{NUM_USERS} users created.')

# 3. Simulation
logs = []

WEATHER_OPTIONS = ['Sunny', 'Rainy', 'Cloudy', 'Snowy']

full_date_range = pd.date_range(start=START_DATE, end=END_DATE)

for user in users:
    satisfaction = 0.0
    boredom_streak = 0

    # user info
    uid = user['user_id']
    u_country = user['country']
    u_group = user['group']
    u_signup = user['signup_date']

    active_days = [d for d in full_date_range if d >= u_signup]

    for date_obj in active_days:
        days_since_signup = (pd.to_datetime(date_obj) - pd.to_datetime(u_signup)).days

        # base visit possibility
        if days_since_signup < 7:
            base_visit = 0.55   # first week, more often
        else:
            base_visit = 0.35   # After D+7, lower base_visit

        visit_prob = base_visit + 0.08 * satisfaction - 0.05 * min(boredom_streak, 5)

        visit_prob = max(0.05, min(visit_prob, 0.85))

        if np.random.random() > visit_prob:
            continue

        raw_weights = [0.01]*6 + [0.04]*5 + [0.06]*7 + [0.08]*6
        
        probs = np.array(raw_weights)
        probs /= probs.sum() 

        hour = np.random.choice(range(0, 24), p=probs)

        month = date_obj.month
        if u_country == 'FR':
            if month in [2,3]:
                weather_probs = [0.2, 0.4, 0.3, 0.1]
            else:
                weather_probs = [0.6, 0.2, 0.2, 0.0]
        else:
            if month in [2,3]:
                weather_probs = [0.5, 0.4, 0.1, 0.0]
            else:
                weather_probs = [0.6, 0.1, 0.3, 0.0]

        weather = np.random.choice(WEATHER_OPTIONS, p=weather_probs)

        card_result = get_context_card(u_country, date_obj, weather, hour)

        # [Step 1] UI simulation - which part do users click
        # 50% -> Click 'Recently Played'
        choose_recently_played = np.random.random() < 0.5

        if choose_recently_played:
            # [common area] Recently Played
            context_id = "Recently_Played_UI"
            card_title = "Recently Played Songs"
            card_genre = "History"
        else:
            # [test area] recommendation section (key code for A/B test)
            if u_group == 'Control':
                # Control
                context_id = "Mixes_Inspired_By"
                card_title = "Discover new tracks similar to your favourites"
                card_genre = "User_Taste_Mix"
            else:
                # Treatment - context card
                context_id = card_result[0]     # ex. Bastille_Day, Morning_Boost
                card_title = card_result[1]
                card_genre = card_result[2]
        
        # 5) Funnel (View -> Click -> Play -> Like)

        # common data
        base_log = {
            'user_id': uid,
            'date': date_obj.strftime('%Y-%m-%d'),
            'hour': hour,
            'weather': weather,
            'context_id': context_id,
            'card_title': card_title,
            'card_genre': card_genre,
            'group': u_group,
            'country': u_country,
            'platform': user['platform'],
            'signup_date': u_signup.strftime('%Y-%m-%d'),
            'days_since_signup': int(days_since_signup),
            'placement': 'recently_played' if choose_recently_played else 'recommendation'
        }

        # Step 1: View (home screen)
        log_view = base_log.copy()
        log_view['action'] = 'view_home'
        logs.append(log_view)

        # Step 2: Click 
        if u_group == 'Treatment' and not choose_recently_played:
            click_prob = 0.65  
        else:
            click_prob = 0.35

        # click simulation
        if np.random.random() < click_prob:
            log_click = base_log.copy()
            log_click['action'] = 'click_card'
            logs.append(log_click)
            satisfaction += 0.6
            boredom_streak = 0

            # Step 3: Play
            if np.random.random() < 0.8:
                log_play = base_log.copy()
                log_play['action'] = 'play'
                logs.append(log_play)
                satisfaction += 0.4 

                # Step 4: Like
                if np.random.random() < 0.2:
                    log_like = base_log.copy()
                    log_like['action'] = 'like'
                    logs.append(log_like)
                    satisfaction += 0.3
            else:
                satisfaction = max(0.0, satisfaction - 0.05)
        else:
            if days_since_signup >= 7:
                boredom_streak += 1
            satisfaction = max(0.0, satisfaction - 0.1)


logs_df = pd.DataFrame(logs)

logs_df.to_csv('music_app_logs.csv', index=False, encoding='utf-8-sig')
print("📂 'music_app_logs.csv' saved successfully!")

print("-" * 30)
print(f"✅ Simulation Complete!")
print(f"총 생성된 로그 수: {len(logs_df):,} rows")
print("-" * 30)

# 결과 미리보기
print(logs_df.head())