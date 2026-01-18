import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta

# 0. 설정 (Configuration)
fake = Faker()
NUM_USERS = 1000  # 유저 수
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 3, 30) # 3개월치 데이터
PLATFORMS = ['iOS', 'Android']
COUNTRIES = ['FR', 'BR'] # 프랑스, 브라질
GROUPS = ['Control', 'Treatment']

# 1. 트리거 로직 함수 (멘트 + 장르 세트 리턴)
def get_context_card(country, date_obj, weather, hour):
    """
    상황(Context)에 따라 (ID, 제목, 장르) 3가지를 반환합니다.
    우선순위: 1.이벤트 -> 2.날씨 -> 3.시간대
    """
    
    # Priority 1: Special Events (국가별 이벤트)
    if country == 'FR' and date_obj.month == 7 and date_obj.day == 14:
        return "Bastille_Day_Vibes", "Parisian Night", "French Electro/Pop"
    
    if country == 'BR' and (date_obj.month == 2 and 9 <= date_obj.day <= 17):
        return "Rio_Carnival_Live", "Samba Energy", "Samba/Pagode"

    # Priority 2: Weather (날씨)
    if weather == 'Rainy':
        return "Rainy_Day_Jazz", "Cozy Jazz for Rain", "Jazz/Lo-fi"
    
    # Priority 3: Daily Routine (시간대)
    if 6 <= hour < 12:
        return "Morning_Boost", "Start your day", "Upbeat Pop", 'Meditation'
    elif 12 <= hour < 18:
        return "Afternoon_Focus", "Lo-fi for Focus", "Energetic Afro", "Energetic Pop"
    elif 18 <= hour < 22:
        return "Evening_Chill", "Relax after work", "R&B/Soul", "Let's party"
    else:
        return "Night_Sleep", "Deep Sleep Sounds", "Ambient/Piano", 'Classical music for sleep'

# 2. 유저 데이터 생성 (User Generation)
users = []
print('Generating users ...')

for i in range(NUM_USERS):
    user_id = i+1
    country = np.random.choice(COUNTRIES, P=[0.5, 0.5]) # FR 50%, BR 50%
    group = np.random.choice(GROUPS, p=[0.5, 0.5]) # A/B Test Group

    days_offset = np.random.randint(0,59)
    signup_date = START_DATE + timedelta(days=days_offset)

    users.append({
        'user_id': user_id,
        'country': country,
        'group': group,
        'signup_date': signup_date,
        'platform': np.random.choice(PLATFORMS)
    })
users_df = pd.DataFrame(users)
print('{NUM_USERS} users created (FR/BR Only).')