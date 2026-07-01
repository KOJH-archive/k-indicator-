import os
import sys
import json
import re
import sqlite3
from datetime import datetime
import google.generativeai as genai

# Reconfigure stdout/stderr to utf-8 to avoid encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from backend.database import get_db_connection
from backend.parser import extract_text


# Load configurations
SETTINGS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "settings.json"))

def load_settings():
    """Load settings from settings.json."""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print("Error loading settings:", e)
    return {}

def extract_period(title, pub_date):
    """Extract YYYY-MM period from article title or publication date."""
    if title:
        # Match "YYYY년 MM월" or "YYYY년 M월"
        match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월', title)
        if match:
            year = match.group(1)
            month = int(match.group(2))
            return f"{year}-{month:02d}"
        
        # Match "YYYY.MM" or "YYYY.M"
        match = re.search(r'(\d{4})\.(\d{1,2})', title)
        if match:
            year = match.group(1)
            month = int(match.group(2))
            if 1 <= month <= 12:
                return f"{year}-{month:02d}"
                
    if pub_date:
        return pub_date[:7]  # YYYY-MM
        
    return datetime.now().strftime("%Y-%m")

def fallback_regex_extractor(text, source, title=None, pub_date=None):
    """
    Fallback extractor using regex when Gemini is not configured.
    Attempts to find base interest rate, CPI YoY, or trade stats.
    """
    indicators = []
    period = extract_period(title, pub_date)
    
    # 1. Bank of Korea Base Interest Rate (기준금리)
    if source == "한국은행" or "기준금리" in text:
        # Match e.g. "기준금리를 현재의 3.50%에서" or "기준금리(3.25%)" or "연 3.25%"
        rate_match = (
            re.search(r'기준금리\s*.*?(\d+\.\d+)\s*%', text) or
            re.search(r'기준금리\s*.*?연\s*(\d+\.\d+)\s*%', text) or
            re.search(r'기준금리를\s*.*?(\d+\.\d+)\s*%로', text)
        )
        if rate_match:
            indicators.append({
                "key": "base_rate",
                "name": "기준금리",
                "value": float(rate_match.group(1)),
                "unit": "%",
                "period": period
            })
            
    # 2. CPI YoY Inflation (소비자물가상승률)
    if "소비자물가" in text or "물가상승률" in text:
        # Match e.g. "소비자물가지수는 전년동월대비 2.4% 상승" or "전년동월대비 2.4%" or "소비자물가 상승률은 2.4%"
        cpi_match = (
            re.search(r'전년동월대비\s*.*?(\d+\.\d+)\s*%', text) or
            re.search(r'소비자물가\s*.*?(\d+\.\d+)\s*%\s*상승', text) or
            re.search(r'물가\s*.*?(\d+\.\d+)\s*%\s*상승', text)
        )
        if cpi_match:
            indicators.append({
                "key": "cpi_yoy",
                "name": "소비자물가상승률",
                "value": float(cpi_match.group(1)),
                "unit": "%",
                "period": period
            })
            
    # 3. Trade Balance (무역수지)
    if "무역수지" in text or "수출" in text:
        # Match trade balance: e.g. "무역수지는 12.5억 달러 흑자" or "무역수지 15억 달러 적자"
        tb_match = re.search(r'무역수지\s*.*?(-?\d+\.?\d*)\s*(?:억\s*달러|억불)(?:\s*(흑자|적자))?', text)
        if tb_match:
            val = float(tb_match.group(1))
            is_deficit = False
            if tb_match.group(2) == '적자':
                is_deficit = True
            else:
                start_pos = tb_match.start()
                snippet = text[start_pos:start_pos+100]
                if '적자' in snippet or '감소' in snippet:
                    is_deficit = True
            
            if is_deficit:
                val = -abs(val)
                
            indicators.append({
                "key": "trade_balance",
                "name": "무역수지",
                "value": val,
                "unit": "억 달러",
                "period": period
            })
            
    # 4. Export Growth (수출증가율)
    if "수출" in text:
        exp_match = (
            re.search(r'수출\s*.*?전년동월대비\s*.*?(-?\d+\.\d+)\s*%\s*(증가|감소)?', text) or
            re.search(r'수출\s*.*?(-?\d+\.\d+)\s*%\s*(증가|감소)', text) or
            re.search(r'수출\s*.*?전년동월대비\s*.*?(\d+\.\d+)\s*%', text) or 
            re.search(r'수출\s*.*?(\d+\.\d+)\s*%\s*증가', text)
        )
        if exp_match:
            val = float(exp_match.group(1))
            is_decrease = False
            if len(exp_match.groups()) >= 2 and exp_match.group(2) == '감소':
                is_decrease = True
            else:
                snippet = text[exp_match.start():exp_match.end()+30]
                if '감소' in snippet or '줄어' in snippet:
                    is_decrease = True
            
            if is_decrease:
                val = -abs(val)
                
            indicators.append({
                "key": "export_growth",
                "name": "수출증가율",
                "value": val,
                "unit": "%",
                "period": period
            })
            
    return indicators


def analyze_document(article_id):
    """
    Load document text, run Gemini API to extract key summary/indicators,
    and save results to SQLite database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch article information
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cursor.fetchone()
    if not article:
        conn.close()
        print(f"Article {article_id} not found.")
        return False
        
    source = article["source"]
    title = article["title"]
    attachments_json = article["attachments"]
    
    # 2. Extract text from attachments (PDF prioritized)
    attachments = []
    if attachments_json:
        try:
            attachments = json.loads(attachments_json)
        except Exception:
            pass
            
    extracted_text = ""
    # Try to find a PDF first, then HWPX, then DOCX
    pdf_attachment = next((a for a in attachments if a["filename"].lower().endswith(".pdf")), None)
    other_attachment = next((a for a in attachments if a["filename"].lower().endswith((".hwpx", ".docx"))), None)
    
    target_attachment = pdf_attachment or other_attachment or (attachments[0] if attachments else None)
    
    if target_attachment:
        local_path = target_attachment["local_path"]
        print(f"Extracting text from: {local_path}")
        extracted_text = extract_text(local_path)
        
    # Save the raw text to DB
    cursor.execute("UPDATE articles SET raw_text = ? WHERE id = ?", (extracted_text, article_id))
    conn.commit()
    
    if not extracted_text:
        print(f"No text extracted for article {article_id}.")
        cursor.execute("UPDATE articles SET status = 'failed' WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        return False
        
    # 3. Check for Gemini API key
    settings = load_settings()
    api_key = settings.get("gemini_api_key", "").strip()
    
    summary = ""
    impact = ""
    indicators = []
    
    if api_key:
        print("Running Gemini AI analysis...")
        try:
            genai.configure(api_key=api_key)
            # Use gemini-1.5-flash for speed and cost-effectiveness
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Shorten text to ~20,000 characters if very long to prevent token issues
            sample_text = extracted_text[:20000]
            
            prompt = f"""
이 보도자료는 한국의 주요 국가 경제지표 발표 자료입니다.
보도자료 원문 텍스트를 읽고 아래 요구사항에 맞게 JSON 형식으로 분석하여 응답해 주세요.

[보도자료 정보]
출처: {source}
제목: {title}

[보도자료 텍스트]
{sample_text}

[요구사항]
반드시 다음 JSON 형식으로만 응답해 주세요. 응답에 백틱(```json)이나 다른 설명 텍스트를 포함하지 말고 순수 JSON 문자열만 출력해 주세요.
주요 경제지표(기준금리, 소비자물가상승률, 수출액, 수입액, 무역수지, 고용률, 실업률 등)가 언급되어 있다면 반드시 indicators 배열에 추가해 주세요.
지표의 period(기간)는 보도자료에서 가리키는 대상 년-월 (예: '2026-06') 또는 구체적인 발표일 (예: '2026-07-01') 형식으로 지정해 주세요.
지표의 key는 다음 규칙을 적용해 주세요:
- BOK 기준금리: 'base_rate'
- 소비자물가상승률(YoY %): 'cpi_yoy'
- 무역수지(억 달러): 'trade_balance'
- 수출증가율(YoY %): 'export_growth'
- 수입증가율(YoY %): 'import_growth'
- 실업률(%): 'unemployment_rate'
- 고용률(%): 'employment_rate'
- 기타 지표는 직관적인 영문 key로 작성 (예: 'industrial_output_yoy')

[JSON 출력 포맷]
{{
  "summary": "보도자료의 핵심 내용을 요약한 한국어 문장 (1-2문장)",
  "impact": "이 발표가 금융 시장 및 실물 경제에 미치는 영향 분석 (1-2문장)",
  "indicators": [
    {{
      "key": "indicator_key",
      "name": "지표의 한글 이름 (예: 소비자물가상승률)",
      "value": 2.4, 
      "unit": "%",
      "period": "지표 대상 기간 (예: 2026-06)"
    }}
  ]
}}
"""
            # Request JSON output
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response JSON
            res_json = json.loads(response.text.strip())
            summary = res_json.get("summary", "")
            impact = res_json.get("impact", "")
            indicators = res_json.get("indicators", [])
            print("Gemini analysis completed successfully.")
            
        except Exception as e:
            print("Error running Gemini API:", e)
            print("Falling back to Regex Extractor...")
            summary = f"보도자료 분석 진행 중 오류가 발생했습니다. ({e})"
            impact = "AI 분석 오류로 시장 영향력을 평가할 수 없습니다."
            indicators = fallback_regex_extractor(extracted_text, source, title, article["pub_date"])
    else:
        print("Gemini API Key is not set in settings.json. Using fallback regex extractor.")
        summary = "API Key 설정이 없어 간이 분석을 진행했습니다. 설정 페이지에서 Gemini API Key를 등록하면 완전한 AI 요약 및 상세 분석을 볼 수 있습니다."
        impact = "Gemini API Key가 비어 있어 시장 분석 정보를 생성할 수 없습니다."
        indicators = fallback_regex_extractor(extracted_text, source, title, article["pub_date"])
        
    # 4. Save analysis to database
    try:
        # Update article summary & status
        cursor.execute("""
            UPDATE articles
            SET summary = ?, impact = ?, status = 'completed'
            WHERE id = ?
        """, (summary, impact, article_id))
        
        # Save individual indicators
        for ind in indicators:
            cursor.execute("""
                INSERT INTO indicators (article_id, indicator_key, indicator_name, value, unit, period, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator_key, period) DO UPDATE SET
                    value = excluded.value,
                    article_id = excluded.article_id,
                    created_at = excluded.created_at
            """, (
                article_id,
                ind["key"],
                ind["name"],
                ind["value"],
                ind.get("unit", ""),
                ind["period"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
        conn.commit()
        print(f"Saved analysis and {len(indicators)} indicators for article {article_id}.")
        return True
    except Exception as e:
        print(f"Error saving analysis to DB for article {article_id}: {e}")
        cursor.execute("UPDATE articles SET status = 'failed' WHERE id = ?", (article_id,))
        conn.commit()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # Test script on first article with pending status
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM articles WHERE status = 'pending' LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        print(f"Analyzing article: {row['title']} (ID: {row['id']})")
        analyze_document(row['id'])
    else:
        print("No pending articles to analyze.")
