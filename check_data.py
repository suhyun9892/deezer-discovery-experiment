import pandas as pd
import sys

# 1. Load Data
print("Loading data...")
try:
    # Read the generated CSV file
    df = pd.read_csv('music_app_logs.csv')
    print("File loaded successfully!")
except FileNotFoundError:
    print("Error: 'music_app_logs.csv' not found. Please run generate_logs.py first.")
    sys.exit()

print("-" * 60)
print("[Data Health Check Report]")
print("-" * 60)

# 2. Basic Data Inspection (Row count, Nulls)
print(f"1. Total Rows: {len(df):,} Rows")
print(f"2. Date Range: {df['date'].min()} ~ {df['date'].max()}")
print(f"3. Total Null Values: {df.isnull().sum().sum()}")
# -> Should be 0 for a clean dataset.

# 3. Check Group Balance
print("-" * 60)
print("4. Group Distribution (Target ~50%):")
print(df['group'].value_counts(normalize=True))
# -> Control and Treatment should be split roughly 50:50.

# 4. [Core] A/B Test CTR Comparison
print("-" * 60)
print("5. CTR (Click-Through Rate) Comparison by Group [Core Check]:")

# Calculate the ratio of 'Play' actions for each group
ctr_df = df.groupby('group')['action'].value_counts(normalize=True).unstack()
print(ctr_df)

try:
    treat_ctr = ctr_df.loc['Treatment', 'Play']
    ctrl_ctr = ctr_df.loc['Control', 'Play']
    diff = treat_ctr - ctrl_ctr
    
    print(f"\n Result: Treatment CTR ({treat_ctr*100:.1f}%) - Control CTR ({ctrl_ctr*100:.1f}%) = {diff*100:.2f}%p Difference")
    
    if diff > 0.03: # Consider success if the difference is > 3%p
        print("Validation Success! (Treatment group shows higher engagement as expected)")
    else:
        print("Warning: CTR difference is insignificant. (Check logic)")
except KeyError:
    print("Error: 'Play' or 'Skip' action is missing in the data.")

# 5. UI Logic Verification (Check if Control group saw the wrong cards)
print("-" * 60)
print("6. Top 3 Contexts for Control Group:")
print(df[df['group'] == 'Control']['context_id'].value_counts().head(3))
# -> Should ONLY show 'Mixes_Inspired_By' and 'Recently_Played_UI'.
# -> If 'Morning_Boost' appears here, it's a bug.

print("\n7. Top 5 Contexts for Treatment Group:")
print(df[df['group'] == 'Treatment']['context_id'].value_counts().head(5))
# -> Should show a diverse mix of context cards (Morning, Rainy, etc.).

print("-" * 60)
print("Validation Complete.")