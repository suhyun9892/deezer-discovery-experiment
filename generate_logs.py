import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta

# 0. 설정 (Configuration)
fake = Faker()
NUM_USERS = 1000  # 유저 수
START_DATE = datetime(2025, 2, 1)
END_DATE = datetime(2025, 7, 31) # 3개월치 데이터
PLATFORMS = ['iOS', 'Android']
COUNTRIES = ['FR', 'BR'] # 프랑스, 브라질
GROUPS = ['Control', 'Treatment']

# 1. 트리거 로직 함수 (멘트 + 장르 세트 리턴)
def get_context_card(country, date_obj, weather, hour):
    """
    상황(Context)에 따라 (ID, 제목, 장르) 3가지를 반환합니다.
    우선순위: 1.이벤트 -> 2.날씨 -> 3.시간대
    """
    
    # Priority 1: Special Events
    if date_obj.month == 2 and date_obj.day == 14:
         return "Valentine_Day", "Romantic Vibes", "R&B/Ballad"
    
    if country == 'BR' and (date_obj.month == 2 and date_obj.day >= 28) or (date_obj.month==3 and date_obj.day <= 5):
        return "Rio_Carnival_Live", "Samba Energy", "Samba/Pagode"
    
    if country == 'FR' and date_obj.month == 7 and date_obj.day == 14:
        return "Bastille_Day_Vibes", "Parisian Night", "French Electro/Pop"
    
    if country == 'FR' and date_obj.month == 6 and date_obj.day == 21:
        return "Music_Festival_Day", "Street Music Party", "Live/Acoustic"
    
    # Priority 2: Weather (날씨)
    if weather == 'Rainy':
        return "Rainy_Day_Jazz", "Cozy Jazz for Rain", "Jazz/Lo-fi"
    elif weather == 'Sunny':
        return "Sunny_Drive", "Driving Hits", "Pop/Rock"
    elif weather == 'Snowy':
        return "Snowy_Cabin", "Winter Warmth", "Acoustic"
    elif weather == 'Cloudy':
        return "Windy_classic", "Calm music", "Peaceful R&B"
    
    # Priority 3: Daily Routine (시간대)
    if 5 <= hour < 12:
        return "Morning_Boost", "Start your day", "Upbeat Pop"
    elif 12 <= hour < 18:
        return "Afternoon_Focus", "Lo-fi for Focus", "Energetic Pop"
    elif 18 <= hour < 22:
        return "Evening_Chill", "Relax after work", "R&B/Soul"
    else:
        return "Night_Sleep", "Deep Sleep Sounds", "Ambient/Piano"

# 2. 유저 데이터 생성 (User Generation)
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
print('{NUM_USERS} users created.')

# 3. 로그 데이터 생성 (Simulation)
logs = []

WEATHER_OPTIONS = ['Sunny', 'Rainy', 'Cloudy', 'Snowy']

full_date_range = pd.date_range(start=START_DATE, end=END_DATE)

for user in users:
    # user info
    uid = user['user_id']
    u_country = user['country']
    u_group = user['group']
    u_signup = user['signup_date']

    active_days = [d for d in full_date_range if d >= u_signup]

    for date_obj in active_days:
        if np.random.random() > 0.4:
            continue
        hour = np.random.choice(
            range(0, 24),
            p = [0.01]*6 + [0.04]*5 + [0.06]*7 + [0.08]*6
        )

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

        # [Step 1] 유저가 앱의 어느 영역을 클릭했는가? (UI 시뮬레이션)
        # 50%는 그냥 습관적으로 상단 'Recently Played'를 클릭함 (그룹 무관 공통)
        is_recent_click = np.random.random() < 0.5

        if is_recent_click:
            # [공통 영역] Recently Played (Control, Treatment 모두 발생 가능)
            context_id = "Recently_Played_UI"
            card_title = "Recently Played Songs"
            card_genre = "History"
        else:
            # [실험 영역] 하단 추천 섹션 (여기가 A/B 테스트 핵심!)
            if u_group == 'Control':
                # Control은 기존 알고리즘(Mixes) 노출
                context_id = "Mixes_Inspired_By"
                card_title = "Discover new tracks similar to your favourites"
                card_genre = "User_Taste_Mix"
            else:
                # Treatment는 상황별(Context) 카드 노출
                context_id = card_result[0]     # 예: Bastille_Day, Morning_Boost
                card_title = card_result[1]
                card_genre = card_result[2]
        
        # 5) 행동 시뮬레이션 (Action)
        # 로직: Treatment 그룹이 '실험 영역(Context Card)'을 봤을 때만 클릭률이 높아야 함
        
        base_prob = 0.40 # 기본 클릭률

        if u_group == 'Treatment' and not is_recent_click:
            # Treatment 그룹이면서 + 실험 영역(Context Card)을 본 경우에만
            # 클릭률 대폭 상승 (상황에 딱 맞는 추천이니까!)
            prob_play = 0.50 
        else:
            # 그 외 (Control 그룹이거나, 그냥 Recently Played 누른 경우)
            prob_play = base_prob

        action = np.random.choice(['Play', 'Skip'], p=[prob_play, 1-prob_play])

        logs.append({
            'user_id': uid,
            'date': date_obj.strftime('%Y-%m-%d'),
            'hour': hour,
            'weather': weather,
            'context_id': context_id,
            'card_title': card_title,
            'card_genre': card_genre,
            'action': action,
            'group': u_group,
            'country': u_country
        })

logs_df = pd.DataFrame(logs)

print("-" * 30)
print(f"✅ Simulation Complete!")
print(f"총 생성된 로그 수: {len(logs_df):,} rows")
print("-" * 30)

# 결과 미리보기
print(logs_df.head())