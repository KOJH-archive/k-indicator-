import os
import sqlite3
import time
import requests
import urllib3
import random
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DB_DIR, "database.sqlite")

def fetch_ecos_data(stat_code, item_code, start_month, end_month, description):
    """Generic function to fetch data from ECOS using pagination."""
    data_dict = {}
    print(f"Fetching {description} ({stat_code}/{item_code}) from {start_month} to {end_month} via ECOS API...")
    
    start_idx = 1
    end_idx = 10
    total_count = 1000 
    
    while start_idx <= total_count:
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/{start_idx}/{end_idx}/{stat_code}/M/{start_month}/{end_month}/{item_code}"
        try:
            r = requests.get(url, verify=False, timeout=10)
            data = r.json()
            
            # Catch 602 error (Rate limit)
            if 'RESULT' in data and 'ERROR' in data['RESULT']['CODE']:
                print(f"ECOS API Error: {data['RESULT']['MESSAGE']}")
                raise Exception("API Limit Reached")
                
            if 'StatisticSearch' not in data:
                break
                
            total_count = data['StatisticSearch']['list_total_count']
            rows = data['StatisticSearch']['row']
            
            for row in rows:
                data_dict[row['TIME']] = float(row['DATA_VALUE'])
                
            print(f"Fetched {min(end_idx, total_count)}/{total_count} records...")
            
            start_idx += 10
            end_idx += 10
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Error fetching data at idx {start_idx}: {e}")
            break
            
    return data_dict

def generate_fallback_data(start_year=1999, end_year=2024, base_val=100.0, min_val=2.0, max_val=150.0):
    """Generate synthetic realistic data for fallback during API blocks."""
    import math
    print(f"Generating fallback mock data from {start_year} to {end_year}...")
    data = {}
    val = base_val
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            time_str = f"{y}{m:02d}"
            # Use sine wave + some noise to keep it bound and realistic
            t = (y - start_year) * 12 + m
            noise = random.uniform(-1, 1)
            
            if base_val > 20: # For housing index
                val = base_val + (t * 0.3) + math.sin(t / 12) * 5 + noise
            else: # For unemployment rate
                val = 3.5 + math.sin(t / 24) * 1.5 + noise * 0.5
                
            data[time_str] = round(max(min_val, min(max_val, val)), 2)
    return data

def process_housing_index():
    start_month = "199901"
    end_month = datetime.now().strftime("%Y%m")
    
    # 901Y062: 주택매매가격지수(KB)
    hpi_data = fetch_ecos_data("901Y062", "*AA", start_month, end_month, "Housing Price Index")
    
    if not hpi_data:
        print("Failed to fetch real Housing Price Index data. Skipping seed.")
        return
        
    entries = []
    for time_str, val in hpi_data.items():
        year = time_str[:4]
        month = time_str[4:]
        entries.append((val, f"{year}-{month}"))
        
    seed_db(entries, 'housing_index', '주택매매가격지수', '2022=100')

def process_unemployment_rate():
    start_month = "199901"
    end_month = datetime.now().strftime("%Y%m")
    
    # 901Y067: 실업률 (I32A)
    unemp_data = fetch_ecos_data("901Y067", "I32A", start_month, end_month, "Unemployment Rate")
    
    if not unemp_data:
        print("Failed to fetch real Unemployment Rate data. Skipping seed.")
        return
        
    entries = []
    for time_str, val in unemp_data.items():
        year = time_str[:4]
        month = time_str[4:]
        entries.append((val, f"{year}-{month}"))
        
    seed_db(entries, 'unemployment_rate', '실업률', '%')

def seed_db(entries, indicator_key, indicator_name, unit):
    if not entries:
        return
        
    print(f"Seeding {len(entries)} records for {indicator_key}...")
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    count = 0
    for val, period in entries:
        cursor.execute("""
            INSERT INTO indicators (article_id, indicator_key, indicator_name, value, unit, period, created_at)
            VALUES (NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_key, period) DO UPDATE SET
                value = excluded.value,
                article_id = excluded.article_id,
                created_at = excluded.created_at
        """, (indicator_key, indicator_name, val, unit, period, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        count += 1
        
    conn.commit()
    conn.close()
    print(f"Successfully seeded {count} entries for {indicator_key}.")

if __name__ == "__main__":
    process_housing_index()
    process_unemployment_rate()
