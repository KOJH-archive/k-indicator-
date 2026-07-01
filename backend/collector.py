import os
import sys
import re
import json
import sqlite3
import urllib.parse
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import feedparser

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


# Watched agencies on korea.kr and their prefixes
WATCHED_AGENCY_PREFIXES = [
    "[산업부]", "[산업통상자원부]", "[산업통상부]",
    "[관세청]",
    "[통계청]", "[국가데이터처]",
    "[기재부]", "[기획재정부]", "[재정경제부]"
]

def clean_filename(filename):
    """Clean filename by removing invalid filesystem characters."""
    filename = urllib.parse.unquote(filename)
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ()[]").strip()
    return filename if filename else "unnamed_file"

def download_file(url, download_dir):
    """
    Download a file from url and save it to download_dir.
    Resolves UTF-8 filename from Content-Disposition header.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        # Extract filename from headers
        filename = None
        content_disp = response.headers.get('Content-Disposition')
        if content_disp:
            # Check for RFC 5987 UTF-8 filename (filename*=utf-8'')
            if "filename*=" in content_disp:
                parts = content_disp.split("filename*=")
                if len(parts) > 1:
                    val = parts[1].split(';')[0].strip()
                    if val.lower().startswith("utf-8''"):
                        filename = urllib.parse.unquote(val[7:])
            if not filename and "filename=" in content_disp:
                parts = content_disp.split("filename=")
                if len(parts) > 1:
                    filename = parts[1].split(';')[0].strip().strip('"').strip("'")
        
        if not filename:
            # Fallback to URL path
            filename = os.path.basename(urllib.parse.urlparse(url).path)
            if not filename or '.' not in filename:
                filename = "downloaded_file.bin"
                
        filename = clean_filename(filename)
        filepath = os.path.join(download_dir, filename)
        
        # Write file in chunks
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        return filepath, filename
    except Exception as e:
        print(f"Failed to download file from {url}: {e}")
        return None, None

def parse_korea_detail(url):
    """Scrape attachment links from korea.kr press release detail page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    attachments = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Korea.kr files are typically in links containing /common/download.do
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.text.strip()
            
            if '/common/download.do' in href:
                full_url = urllib.parse.urljoin("https://www.korea.kr", href)
                
                # We only want document extensions (PDF, HWP, HWPX, DOCX)
                # Filter out image formats or empty extensions
                ext_match = re.search(r'\.(pdf|hwp|hwpx|docx)$', text.lower())
                if ext_match or any(k in href.lower() for k in ['fileid=', 'download']):
                    attachments.append({
                        "name": text if text else "attachment",
                        "url": full_url
                    })
        return attachments
    except Exception as e:
        print(f"Error scraping detail page {url}: {e}")
        return []

def parse_bok_detail(url):
    """Scrape BOK detail page to extract attachment download links."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    attachments = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # BOK files are in relative links starting with /fileSrc/portal/
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.text.strip()
            
            if '/fileSrc/portal/' in href:
                full_url = urllib.parse.urljoin("https://www.bok.or.kr", href)
                # Ignore non-document links if they are previewers
                if 'viewer.html' in href or 'docViewer.do' in href:
                    continue
                attachments.append({
                    "name": text if text else "BOK Attachment",
                    "url": full_url
                })
        return attachments
    except Exception as e:
        print(f"Error scraping BOK detail page {url}: {e}")
        return []

def fetch_korea_rss():
    """Fetch and filter latest releases from korea.kr RSS feed."""
    print("Fetching korea.kr RSS feed...")
    rss_url = "https://www.korea.kr/rss/pressrelease.xml"
    feed = feedparser.parse(rss_url)
    
    new_articles = []
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for entry in feed.entries:
        title = entry.title
        link = entry.link
        
        # Preserve newsId parameter for korea.kr detail views
        clean_link = link
        
        # Check if the title starts with any watched prefix
        matched_prefix = None
        for prefix in WATCHED_AGENCY_PREFIXES:
            if title.startswith(prefix):
                matched_prefix = prefix
                break
                
        if not matched_prefix:
            continue
            
        # Determine source name based on prefix
        source = "재정경제부"
        if "산업" in matched_prefix:
            source = "산업통상부"
        elif "관세" in matched_prefix:
            source = "관세청"
        elif "데이터" in matched_prefix or "통계" in matched_prefix:
            source = "국가데이터처"
            
        # Check if already exists in DB
        cursor.execute("SELECT id FROM articles WHERE link = ?", (clean_link,))
        if cursor.fetchone():
            continue
            
        # Convert pubDate to standard YYYY-MM-DD
        # feedparser handles date parsing
        pub_dt = entry.get('published_parsed')
        if pub_dt:
            pub_date = datetime(*pub_dt[:6]).strftime("%Y-%m-%d")
        else:
            pub_date = datetime.now().strftime("%Y-%m-%d")
            
        new_articles.append({
            "source": source,
            "title": title,
            "link": clean_link,
            "pub_date": pub_date
        })
        
    conn.close()
    print(f"Found {len(new_articles)} new watched articles in RSS.")
    return new_articles

def fetch_korea_list_backfill(pages=1):
    """Backfill older articles from korea.kr by crawling the listing page."""
    print(f"Backfilling korea.kr list (pages={pages})...")
    new_articles = []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    target_agencies = {
        "관세청": "관세청",
        "산업통상자원부": "산업통상부",
        "산업통상부": "산업통상부",
        "산업부": "산업통상부",
        "통계청": "국가데이터처",
        "국가데이터처": "국가데이터처",
        "기획재정부": "재정경제부",
        "재정경제부": "재정경제부",
        "기재부": "재정경제부"
    }
    
    for page in range(1, pages + 1):
        url = f"https://www.korea.kr/news/pressReleaseList.do?pageIndex={page}"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/briefing/pressReleaseView.do' in href:
                    clean_link = urllib.parse.urljoin("https://www.korea.kr", href)
                    
                    # Extract title from <strong>
                    strong_tag = link.find('strong')
                    if not strong_tag:
                        continue
                    title = strong_tag.text.strip().replace('\n', ' ')
                    
                    # Extract agency from span.source
                    source_elem = link.find(class_='source')
                    agency_name = ""
                    if source_elem:
                        spans = source_elem.find_all('span')
                        if len(spans) >= 2:
                            agency_name = spans[1].text.strip()
                            
                    if agency_name not in target_agencies:
                        continue
                        
                    source = target_agencies[agency_name]
                    
                    # Check if already in DB
                    cursor.execute("SELECT id FROM articles WHERE link = ?", (clean_link,))
                    if cursor.fetchone():
                        continue
                        
                    # Find date in listing
                    pub_date = datetime.now().strftime("%Y-%m-%d")
                    if source_elem:
                        spans = source_elem.find_all('span')
                        if len(spans) >= 1:
                            date_text = spans[0].text.strip()
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2}', date_text)
                            if date_match:
                                pub_date = date_match.group(0).replace('.', '-')
                                
                    new_articles.append({
                        "source": source,
                        "title": title,
                        "link": clean_link,
                        "pub_date": pub_date
                    })
        except Exception as e:
            print(f"Error backfilling page {page}: {e}")
            
    conn.close()
    return new_articles

def fetch_bok_list(pages=1):
    """Fetch BOK press releases from AJAX board."""
    print(f"Fetching BOK press releases list (pages={pages})...")
    new_articles = []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    url = "https://www.bok.or.kr/portal/singl/newsData/listCont.do"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    for page in range(1, pages + 1):
        params = {
            "menuNo": "201263",
            "pageIndex": str(page)
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all <li class="bbsRowCls">
            rows = soup.find_all('li', class_='bbsRowCls')
            for row in rows:
                link_elem = row.find('a', class_='title')
                if not link_elem:
                    continue
                    
                title = link_elem.text.strip().replace('\n', ' ')
                href = link_elem['href']
                full_link = urllib.parse.urljoin("https://www.bok.or.kr", href)
                
                # Check if already in DB
                cursor.execute("SELECT id FROM articles WHERE link = ?", (full_link,))
                if cursor.fetchone():
                    continue
                    
                # Extract date
                pub_date = datetime.now().strftime("%Y-%m-%d")
                date_span = row.find(class_='date')
                if date_span:
                    date_match = re.search(r'\d{4}\.\d{2}\.\d{2}', date_span.text)
                    if date_match:
                        # Convert YYYY.MM.DD to YYYY-MM-DD
                        pub_date = date_match.group(0).replace('.', '-')
                        
                new_articles.append({
                    "source": "한국은행",
                    "title": title,
                    "link": full_link,
                    "pub_date": pub_date
                })
        except Exception as e:
            print(f"Error fetching BOK page {page}: {e}")
            
    conn.close()
    return new_articles

def save_and_download_article(article, download_dir):
    """
    Scrape detail page, download document attachments,
    and save article metadata to database.
    """
    link = article["link"]
    source = article["source"]
    title = article["title"]
    pub_date = article["pub_date"]
    
    print(f"Processing new release: {title} ({source})")
    
    # Get attachment links from detail page
    if source == "한국은행":
        attachment_links = parse_bok_detail(link)
    else:
        attachment_links = parse_korea_detail(link)
        
    downloaded_files = []
    
    # Download attachment files
    for att in attachment_links:
        print(f"  Downloading attachment: {att['name']} from {att['url']}")
        filepath, filename = download_file(att["url"], download_dir)
        if filepath:
            downloaded_files.append({
                "original_name": att["name"],
                "filename": filename,
                "local_path": filepath
            })
            
    # Save to database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO articles (source, title, link, pub_date, fetch_date, status, attachments)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (
            source,
            title,
            link,
            pub_date,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(downloaded_files)
        ))
        conn.commit()
        print(f"Saved {title} to DB with {len(downloaded_files)} attachments.")
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Already exists, fetch ID
        cursor.execute("SELECT id FROM articles WHERE link = ?", (link,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"Error inserting article {title} into DB: {e}")
        return None
    finally:
        conn.close()

def collect_new_releases():
    """
    Main collector runner:
    1. Fetch BOK releases (latest 3 pages).
    2. Fetch Korea.kr RSS.
    3. Backfill Korea.kr list (first 3 pages).
    4. Scrape details and download attachments.
    """
    download_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "downloads"))
    os.makedirs(download_dir, exist_ok=True)
    
    all_new = []
    # 1. Fetch from BOK list (3 pages)
    all_new.extend(fetch_bok_list(pages=3))
    
    # 2. Fetch from Korea.kr RSS
    all_new.extend(fetch_korea_rss())
    
    # 3. Backfill from Korea.kr list (30 pages)
    all_new.extend(fetch_korea_list_backfill(pages=30))
    
    saved_ids = []
    for art in all_new:
        art_id = save_and_download_article(art, download_dir)
        if art_id:
            saved_ids.append(art_id)
            
    return saved_ids


if __name__ == "__main__":
    # Test script locally
    from backend.database import init_db
    init_db()
    
    print("\n--- Running test collection ---")
    new_ids = collect_new_releases()
    print(f"Collected {len(new_ids)} new articles.")
