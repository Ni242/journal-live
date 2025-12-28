# preview_csv.py
import pandas as pd
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "recent.csv"
df = pd.read_csv(path, encoding='utf-8', low_memory=False)
print("COLUMNS:")
print(df.columns.tolist())
print("\nFIRST 10 ROWS:")
print(df.head(10).to_dict(orient='records'))
