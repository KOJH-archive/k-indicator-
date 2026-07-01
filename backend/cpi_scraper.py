import os
import sqlite3
import time
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DB_DIR, "database.sqlite")

def fetch_cpi_index_data():
    """Fetch monthly CPI index data from BOK ECOS sample API (1998-current)."""
    # 1998 is needed to calculate 1999 YoY
    start_month = "199801"
    end_month = datetime.now().strftime("%Y%m")
    
    cpi_data = {}
    
    # We will use the sample API which allows 10 rows per request.
    # Total rows = ~320. We will make ~32 requests.
    print(f"Fetching CPI index data from {start_month} to {end_month} via ECOS API...")
    
    start_idx = 1
    end_idx = 10
    total_count = 1000  # Will be updated on first request
    
    while start_idx <= total_count:
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/{start_idx}/{end_idx}/901Y010/M/{start_month}/{end_month}/00"
        try:
            r = requests.get(url, verify=False, timeout=10)
            data = r.json()
            
            if 'StatisticSearch' not in data:
                print(f"API Error or Rate Limit hit at {start_idx}: {data}")
                break
                
            total_count = data['StatisticSearch']['list_total_count']
            rows = data['StatisticSearch']['row']
            
            for row in rows:
                time_str = row['TIME']  # e.g., '199901'
                val = float(row['DATA_VALUE'])
                cpi_data[time_str] = val
                
            print(f"Fetched {end_idx}/{total_count} records...")
            
            start_idx += 10
            end_idx += 10
            
            # Sleep to be polite and avoid rate limits
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Error fetching data at idx {start_idx}: {e}")
            break
            
    return cpi_data

def compute_and_seed_yoy(cpi_data):
    """Compute YoY percentage change and insert into database."""
    if not cpi_data:
        print("No CPI data fetched.")
        return False
        
    yoy_entries = []
    
    for time_str, current_val in cpi_data.items():
        year = int(time_str[:4])
        month = time_str[4:]
        
        # Look for previous year's month
        prev_year = year - 1
        prev_time_str = f"{prev_year}{month}"
        
        if prev_time_str in cpi_data:
            prev_val = cpi_data[prev_time_str]
            yoy_val = round(((current_val / prev_val) - 1.0) * 100, 2)
            
            period = f"{year}-{month}"
            yoy_entries.append((yoy_val, period))
            
    if not yoy_entries:
        print("Could not compute any YoY data (missing previous year data).")
        return False
        
    print(f"Computed {len(yoy_entries)} CPI YoY records. Seeding database...")
    
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    count = 0
    for val, period in yoy_entries:
        cursor.execute("""
            INSERT INTO indicators (article_id, indicator_key, indicator_name, value, unit, period, created_at)
            VALUES (NULL, 'cpi_yoy', '소비자물가상승률', ?, '%', ?, ?)
            ON CONFLICT(indicator_key, period) DO UPDATE SET
                value = excluded.value,
                article_id = excluded.article_id,
                created_at = excluded.created_at
        """, (val, period, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        count += 1
        
    conn.commit()
    conn.close()
    
    print(f"Successfully seeded {count} historical CPI YoY entries.")
    return True

if __name__ == "__main__":
    cpi_idx_data = fetch_cpi_index_data()
    compute_and_seed_yoy(cpi_idx_data)
