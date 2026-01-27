import pandas as pd
import sys

# 1. Load Data
print("Loading data...")
try:
    # Load the newly generated data through October.
    df = pd.read_csv('music_app_logs.csv')
    print("File loaded successfully!")
except FileNotFoundError:
    print("Error: 'music_app_logs.csv' not found. Please run generate_logs.py first.")
    sys.exit()

print("-" * 60)
print("[Data Health Check Report - Global Markets (FR, BR, DE)]")
print("-" * 60)

# 2. Basic Data Inspection
print(f"1. Total Rows: {len(df):,} Rows")
print(f"2. Date Range: {df['date'].min()} ~ {df['date'].max()}")
print(f"3. Total Null Values: {df.isnull().sum().sum()}")

# 3. Country & Group Balance
print("-" * 60)
print("4. Country Distribution (Check for DE):")
print(df['country'].value_counts(normalize=True))
print(f"\n5. Group Distribution (Target ~50%):")
print(df['group'].value_counts(normalize=True))

# 4. [Core] A/B Test CTR Comparison
print("-" * 60)
print("6. CTR (Click-Through Rate) Comparison by Group:")

# Handle 'play' action flexibly as it might be lowercase depending on the generation logic.
ctr_df = df.groupby('group')['action'].value_counts(normalize=True).unstack()
print(ctr_df)

# Identify whether 'play' or 'Play' exists in the columns and calculate.
play_col = 'play' if 'play' in ctr_df.columns else 'Play'

try:
    treat_ctr = ctr_df.loc['Treatment', play_col]
    ctrl_ctr = ctr_df.loc['Control', play_col]
    diff = treat_ctr - ctrl_ctr
    
    print(f"\n Result: Treatment CTR ({treat_ctr*100:.1f}%) - Control CTR ({ctrl_ctr*100:.1f}%) = {diff*100:.2f}%p Difference")
    
    # Success if the difference is > 2%p when expanded to 3 countries.
    if diff > 0.02: 
        print("Validation Success! (Treatment group shows higher engagement)")
    else:
        print("Warning: CTR difference is lower than expected.")
except KeyError:
    print(f"Error: Action '{play_col}' is missing in the data.")

# 5. [Crucial] Special Event Context Check (Including Germany)
print("-" * 60)
print("7. Special Event Context Check (Treatment Group Only):")

# Target list including German Oktoberfest and May Day.
target_contexts = [
    'Valentine_Day', 
    'Music_Festival_Day', 
    'Bastille_Day_Vibes', 
    'Rio_Carnival_Live',
    'Oktoberfest_Schlager'
]

treatment_df = df[df['group'] == 'Treatment']
context_counts = treatment_df['context_id'].value_counts()

for ctx in target_contexts:
    cnt = context_counts.get(ctx, 0)
    # Oktoberfest lasts longer, so it should naturally have a higher count.
    status = "🔥 HOT (Good)" if cnt > 15 else "⚠️ LOW/MISSING"
    print(f"- {ctx}: {cnt}건 발견 -> {status}")

# 6. Germany (DE) Specific Logic Check
print("-" * 60)
print("8. Top 5 Contexts for Germany (DE) - Treatment Group Only:")
de_check = df[(df['country'] == 'DE') & (df['group'] == 'Treatment')]
if not de_check.empty:
    print(de_check['context_id'].value_counts().head(5))
else:
    print("Warning: No Germany (DE) data found in Treatment group!")

# 7. UI Logic Verification (Overall)
print("-" * 60)
print("9. UI Logic Verification (Should not overlap):")
print("\n[Control Group - Should ONLY be Generic]")
print(df[df['group'] == 'Control']['context_id'].value_counts().head(3))

print("\n[Treatment Group - Should be Diverse]")
print(df[df['group'] == 'Treatment']['context_id'].value_counts().head(10))

print("-" * 60)
print("Final Validation Complete. Ready for BigQuery Overwrite & dbt run!")