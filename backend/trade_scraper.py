import os
import sqlite3
import time
import requests
import urllib3
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
    total_count = 1000  # Will be updated on first request
    
    while start_idx <= total_count:
        # Note: the URL format needs the item_code at the end
        # URL: /api/StatisticSearch/sample/json/kr/start/end/STAT_CODE/M/START_MONTH/END_MONTH/ITEM_CODE1
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/{start_idx}/{end_idx}/{stat_code}/M/{start_month}/{end_month}/{item_code}"
        try:
            r = requests.get(url, verify=False, timeout=10)
            data = r.json()
            
            if 'StatisticSearch' not in data:
                print(f"API Error or Rate Limit hit at {start_idx}: {data}")
                break
                
            total_count = data['StatisticSearch']['list_total_count']
            rows = data['StatisticSearch']['row']
            
            for row in rows:
                time_str = row['TIME']
                val = float(row['DATA_VALUE'])
                data_dict[time_str] = val
                
            print(f"Fetched {min(end_idx, total_count)}/{total_count} records...")
            
            start_idx += 10
            end_idx += 10
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Error fetching data at idx {start_idx}: {e}")
            break
            
    return data_dict

def process_trade_balance():
    """Fetch trade balance (상품수지) and seed DB."""
    start_month = "199901"
    end_month = datetime.now().strftime("%Y%m")
    # 301Y013 (국제수지) / 100000 (상품수지)
    tb_data = fetch_ecos_data("301Y013", "100000", start_month, end_month, "Trade Balance")
    
    entries = []
    for time_str, val in tb_data.items():
        year = time_str[:4]
        month = time_str[4:]
        period = f"{year}-{month}"
        
        # Convert from million USD to 100 million USD (억 달러)
        val_100m = round(val / 100, 2)
        entries.append((val_100m, period))
        
    seed_db(entries, 'trade_balance', '무역수지', '억 달러')

def process_export_growth():
    """Fetch export index, compute YoY growth, and seed DB."""
    start_month = "199801" # Need 1998 to compute 1999 YoY
    end_month = datetime.now().strftime("%Y%m")
    # 403Y001 (수출금액지수) / *AA (총지수)
    exp_idx_data = fetch_ecos_data("403Y001", "*AA", start_month, end_month, "Export Index")
    
    entries = []
    for time_str, current_val in exp_idx_data.items():
        year = int(time_str[:4])
        month = time_str[4:]
        
        prev_year = year - 1
        prev_time_str = f"{prev_year}{month}"
        
        if prev_time_str in exp_idx_data:
            prev_val = exp_idx_data[prev_time_str]
            yoy_val = round(((current_val / prev_val) - 1.0) * 100, 2)
            period = f"{year}-{month}"
            entries.append((yoy_val, period))
            
    seed_db(entries, 'export_growth', '수출증가율', '%')

def seed_db(entries, indicator_key, indicator_name, unit):
    if not entries:
        print(f"No entries to seed for {indicator_key}.")
        return False
        
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
    return True

if __name__ == "__main__":
    process_trade_balance()
    process_export_growth()
