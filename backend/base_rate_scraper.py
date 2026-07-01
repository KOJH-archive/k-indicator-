import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# Set up the database path
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DB_DIR, "database.sqlite")

def scrape_and_seed_base_rates():
    """Scrape BOK historical base rates and insert into database."""
    url = "https://www.bok.or.kr/portal/singl/baseRate/list.do"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "dataSeCd": "01",
        "menuNo": "200643"
    }
    
    print("Scraping historical BOK base rates from web...")
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        table = soup.find('table')
        if not table:
            print("Could not find the base rate table on BOK website.")
            return False
            
        rows = table.find_all('tr')
        rate_entries = []
        
        for tr in rows:
            tds = tr.find_all('td')
            # The rows we want have exactly 3 cells
            if len(tds) < 3:
                continue
            
            year_text = tds[0].text.strip()
            month_day_text = tds[1].text.strip()
            rate_text = tds[2].text.strip()
            
            # Parse rate
            try:
                rate_val = float(rate_text)
            except ValueError:
                continue
            
            # Extract year
            year_match = re.search(r'\d{4}', year_text)
            if not year_match:
                continue
            year = year_match.group(0)
            
            # Extract month
            month_match = re.search(r'(\d+)\s*월', month_day_text)
            if not month_match:
                continue
            month = f"{int(month_match.group(1)):02d}"
            
            period = f"{year}-{month}"
            rate_entries.append((rate_val, period))
        
        if not rate_entries:
            print("No valid base rate entries parsed.")
            return False
            
        print(f"Parsed {len(rate_entries)} historical base rates. Seeding database...")
        
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        count = 0
        for rate, period in rate_entries:
            # Insert into indicators table
            cursor.execute("""
                INSERT INTO indicators (article_id, indicator_key, indicator_name, value, unit, period, created_at)
                VALUES (NULL, 'base_rate', '기준금리', ?, '%', ?, ?)
                ON CONFLICT(indicator_key, period) DO UPDATE SET
                    value = excluded.value,
                    article_id = excluded.article_id,
                    created_at = excluded.created_at
            """, (rate, period, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            count += 1
            
        conn.commit()
        conn.close()
        print(f"Successfully seeded {count} historical base rate entries.")
        return True
        
    except Exception as e:
        print(f"Error seeding base rates: {e}")
        return False

if __name__ == "__main__":
    scrape_and_seed_base_rates()
