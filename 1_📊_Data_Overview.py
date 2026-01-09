# File: pages/1_📊_Data_Overview.py
# THE FINAL, ROBUST VERSION with HTTP Status Check, Requests Fallback, Shell Optimization, Enhanced Oxylabs, and Telegram Resolution

import streamlit as st
import pandas as pd
from datetime import timedelta, datetime, date
import time
import re
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup, Tag
from langdetect import detect, LangDetectException
from urllib.parse import urlparse, urljoin, unquote
import tldextract 
import concurrent.futures
from dateutil.relativedelta import relativedelta
import requests

from common import (
    fetch_data_for_range, run_api_importer, ABS_MIN_DATE, ABS_MAX_DATE,
    supabase, client as openai_client, delete_serp_data_by_date_range
)

# --- YOUR API CREDENTIALS ---
OXYLABS_USERNAME = "insseo88_Rc25c"
OXYLABS_PASSWORD = "Qq511800000~"
GOOGLE_API_KEY = "AIzaSyALkbMC1snaevKowWWBkXLFwibrIURlIsk"

# //======================================================================//
# //======= ALL ADVANCED SCANNING FUNCTIONS (PRESERVED) ==================//
# //======================================================================//

# --- 1. PERFORMANCE / TECHNICAL METRICS ---

def get_website_speed(domain: str) -> tuple[int, int]:
    mobile_score, desktop_score = 0, 0
    for strategy in ['mobile', 'desktop']:
        api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://{domain}&key={GOOGLE_API_KEY}&strategy={strategy}"
        try:
            response = requests.get(api_url, timeout=90)
            response.raise_for_status()
            data = response.json()
            score = int(data['lighthouseResult']['categories']['performance']['score'] * 100)
            if strategy == 'mobile': mobile_score = score
            else: desktop_score = score
        except Exception: pass 
    return mobile_score, desktop_score

def _fetch_url_content(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'})
        response.raise_for_status()
        return response.text
    except requests.RequestException: return None

def get_sitemap_path_count(domain: str) -> int:
    extracted = tldextract.extract(domain); root_domain = f"{extracted.domain}.{extracted.suffix}"; base_url = f"https://{root_domain}"
    potential_sitemaps = [f"{base_url}/sitemap.xml", f"{base_url}/sitemap_index.xml", f"{base_url}/robots.txt"]
    sitemap_urls = set(); sitemap_content = None
    for url in potential_sitemaps:
        content = _fetch_url_content(url)
        if content:
            if url.endswith('robots.txt'):
                for line in content.splitlines():
                    if line.lower().startswith('sitemap:'): sitemap_urls.add(line.split(':', 1)[-1].strip())
            elif '<sitemapindex' in content: sitemap_content = content; break
            elif '<urlset' in content: sitemap_urls.add(url); break
    if sitemap_content:
        try:
            root = ET.fromstring(sitemap_content) 
            for sitemap_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                 sitemap_urls.add(sitemap_elem.text)
        except ET.ParseError: pass
    total_paths = 0
    for sitemap_url in sitemap_urls:
        sitemap_xml = _fetch_url_content(sitemap_url)
        if sitemap_xml:
            try: total_paths += len(BeautifulSoup(sitemap_xml, 'xml').find_all('loc'))
            except Exception: pass
    return total_paths

# --- 2. WHOIS AND WAYBACK HELPERS ---

def _fetch_whois_data(domain: str) -> str | None:
    """
    ROBUST VERSION: Handles RapidAPI (Domain Guru) varied date formats.
    Returns: "18 Y, 10 M" or None
    """
    url = "https://domainguru.p.rapidapi.com/info"
    
    headers = {
        "x-rapidapi-key": "c27ae34295msh5871275f9de10f2p1654a0jsn551e72dd225e",
        "x-rapidapi-host": "domainguru.p.rapidapi.com"
    }
    
    querystring = {"domain": domain}

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        # 如果 API 报错（404/500），直接返回 None
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        # 1. 尝试提取 creationDate
        raw_date = data.get('creationDate')
        
        # 后备方案：如果顶层没有，从 whoisData 里找
        if not raw_date and 'whoisData' in data:
            if isinstance(data['whoisData'], dict):
                for key, record in data['whoisData'].items():
                     if isinstance(record, dict) and 'data' in record:
                         raw_date = record['data'].get('creationDate')
                         if raw_date: break
            elif isinstance(data['whoisData'], list):
                for record in data['whoisData']:
                    if 'data' in record:
                         raw_date = record['data'].get('creationDate')
                         if raw_date: break

        # 2. 如果还是没找到，直接返回
        if not raw_date:
            return None

        # 3. 🛡️ 核心修复：处理各种奇怪的数据类型 🛡️
        from dateutil import parser
        creation_dt = None

        try:
            # 情况 A: 这是一个列表 (例如 ['2023-01-01'])
            if isinstance(raw_date, list):
                if len(raw_date) > 0:
                    raw_date = raw_date[0]
                else:
                    return None

            # 情况 B: 这是一个 Unix 时间戳 (整数或浮点数)
            if isinstance(raw_date, (int, float)):
                # 检查是否是毫秒级时间戳 (如果是13位数字，通常是毫秒)
                if raw_date > 100000000000: 
                    raw_date = raw_date / 1000
                creation_dt = datetime.fromtimestamp(raw_date)
            
            # 情况 C: 这是一个字符串，尝试解析
            else:
                str_date = str(raw_date).strip()
                if not str_date or str_date.lower() == "none":
                    return None
                creation_dt = parser.parse(str_date)

        except (ValueError, TypeError, OverflowError):
            # 如果解析彻底失败 (例如格式是 "Unknown Date")
            return None

        # 4. 计算年龄
        if creation_dt:
            # 确保 naive time (移除时区以进行减法)
            creation_dt = creation_dt.replace(tzinfo=None)
            now = datetime.now()

            # 防止出现未来的日期 (API 数据错误)
            if creation_dt > now:
                return "0 Y, 0 M"

            diff = relativedelta(now, creation_dt)
            return f"{diff.years} Y, {diff.months} M"
            
        return None

    except Exception:
        # 全局兜底，防止 crash
        return None

def _fetch_wayback_data(domain: str) -> str | None:
    """
    获取 Wayback Machine 的第一次抓取时间，并计算距今多久。
    返回格式: "X Y, Z M" (与 Whois 格式保持一致)
    """
    try:
        # limit=1 & sort=closest (或者默认第一条) 获取最早记录
        cdx_url = f"https://web.archive.org/cdx/search/cdx?url={domain}&output=json&limit=1&filter=statuscode:200"
        
        response = requests.get(cdx_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if len(data) > 1 and len(data[1]) > 1:
            timestamp = data[1][1]  # 格式通常是 "20070119192824" (YYYYMMDDHHMMSS)
            
            if len(timestamp) >= 8:
                # 1. 解析日期字符串 (只取前8位 YYYYMMDD 即可，或者完整解析)
                # Wayback 时间戳通常是 UTC，这里简单作为 naive time 处理
                year = int(timestamp[:4])
                month = int(timestamp[4:6])
                day = int(timestamp[6:8])
                
                first_seen_date = datetime(year, month, day)
                now = datetime.now()
                
                # 2. 计算时间差
                from dateutil.relativedelta import relativedelta # 确保顶部导入了
                diff = relativedelta(now, first_seen_date)
                
                # 3. 格式化输出 "X Y, Z M"
                return f"{diff.years} Y, {diff.months} M"
                
        return None
        
    except Exception:
        return None

# NEW FUNCTION: Check initial HTTP Status
def _get_initial_http_status(domain: str) -> str:
    """Performs a quick request to get the final HTTP status code after redirects."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
        # Use GET to follow redirects (HEAD can sometimes be blocked or inaccurate)
        response = requests.get(f"https://{domain}", headers=headers, timeout=10, allow_redirects=True, stream=True)
        response.close() # Close connection immediately after reading headers
        
        status_code = response.status_code
        reason = response.reason if response.reason else "Status Reason Unknown"
        
        return f"{status_code} {reason}"
        
    except requests.exceptions.Timeout:
        return "Timeout"
    except requests.exceptions.HTTPError as e:
        # Catch explicit 4xx/5xx responses
        return f"{e.response.status_code} {e.response.reason}"
    except requests.exceptions.ConnectionError as e:
        # Catch DNS or connection refusal errors
        return "DNS/Connection Error"
    except Exception as e:
        return f"Request Failed ({type(e).__name__})"
    
def _is_money_site_by_content(content_lower: str) -> bool:
    """
    通过关键词组合判断是否为 Money Site。
    逻辑：不依赖具体品牌名 (lvking)，而是依赖 '行业通用词' + '动作/交易词' 的组合。
    """
    
    # 1. 行业通用词 (Industry Categories)
    # 这些词描述了网站提供什么服务。不管它叫什么牌子，它肯定得提这些词。
    gambling_industry_keywords = [
        'online casino', 'live casino', 'sportsbook', 'sbo', 'ibc', # 截图里的 Sportsbook, Live Casino
        'slot game', 'slots', 'jackpot', 'arcade', 'fishing game',  # 截图里的 Slot
        '4d lottery', '4d result', 'magnum 4d', 'damacai',          # 截图里的 4D
        'poker', 'baccarat', 'roulette', 'sicbo', 'blackjack',
        'betting', 'gambling', 'e-sports betting',
        'mega888', '918kiss', 'pussy888' # 这几个太大了，已成为品类代名词，建议保留
    ]

    # 2. 动作与交易词 (Actions & Transactions)
    # 截图里非常明显的 "Sign Up", "Deposit", "Withdraw", "Promotion"
    action_transaction_keywords = [
        'deposit', 'withdraw', 'top up', 'cuci',   # 资金相关
        'welcome bonus', 'rebate', 'promotion', 'free credit', # 优惠相关
        'register', 'sign up', 'login', 'join now', 'play now', # 注册相关
        'download', 'apk', 'app download', 'install' # 下载相关
    ]

    # --- 核心判断逻辑 ---
    
    # 检查 A: 是否包含行业词
    has_industry_kw = any(k in content_lower for k in gambling_industry_keywords)
    
    # 检查 B: 是否包含动作/交易词
    has_action_kw = any(k in content_lower for k in action_transaction_keywords)
    
    # 检查 C: 是否包含联系方式 (WhatsApp/Telegram/WeChat)
    has_contact = ('whatsapp' in content_lower or 'telegram' in content_lower or 'wechat' in content_lower)

    # 判定规则：
    # 规则 1: (行业词 + 动作词) -> 肯定是 Money Site 
    # 例如: "Live Casino" (行业) + "Deposit" (动作) = 100% 博彩
    if has_industry_kw and has_action_kw:
        return True

    # 规则 2: (行业词 + 联系方式) -> 肯定是 Money Site / Agent
    # 例如: "Mega888" (行业) + "WhatsApp" (联系) = 代理
    if has_industry_kw and has_contact:
        return True
        
    return False

def analyze_domain_type_with_ai(domain: str, content: str) -> str:
    if content == "MINIMAL_CONTENT_ERROR" or not content: 
        return 'Unreachable' 
        
    content_lower = content.lower()
    
    # --- 1. Money Site Check (Highest Priority) ---
    is_money_site_content = _is_money_site_by_content(content_lower)
    if is_money_site_content: 
        return "Money Site"

    # --- 2. Shell Check (TLD check) ---
    is_shell_domain = '.gov' in domain.lower() or '.edu' in domain.lower()
    if is_shell_domain:
        return "Shell"

    # --- 3. Fallback to AI Classification ---
    
    system_prompt = (
            "You are an expert SEO analyst. Your task is to categorize a website's primary purpose. "
            "A Python script has already performed a basic check for 'Money Sites' and 'Shells', but it may have missed some cases (false negatives). " # 修改点 1：告诉 AI 脚本可能出错
            "Respond with a JSON object containing one key: 'type'. "
            "Classify the domain based on the following rules in priority order:\n\n"
            
            "A. **Money Site** (Fallback Check):\n" # 修改点 2：把这个加回来作为最高优先级
            "  - Trigger: The content clearly promotes online gambling, casinos, betting, slots, or requires downloading a gambling app, even if the user didn't explicitly mention it.\n"
            "  - Action: Classify as 'Money Site'.\n\n"

            "B. **Social Media**:\n"
            "  - Trigger: The website's core function is centered around user-generated content, profiles, sharing, messaging, or community interaction.\n"
            "  - Action: Classify as 'Social Media'.\n\n"

            "C. **Review Site**:\n"
            "  - Trigger: The content contains review-related keywords ('review', 'top 10', 'guide') OR general gambling keywords, but the site's primary purpose is informational or comparative."
            "  - Condition: Look for long articles, comparison tables, and an absence of direct play/deposit features."
            "  - Action: Classify as 'Review Site'.\n\n"

            "D. **General**:\n"
            "  - Trigger: The website is accessible but does not fit any of the above categories.\n"
            "  - Action: Classify as 'General'."
        )
    user_prompt = f"Analyze:\nDomain: {domain}\nContent Snippet: \"{content[:4000]}\""
    try:
        # Call AI for semantic classification of Social Media / Review Site / General
        response = openai_client.chat.completions.create(model="gpt-4o", response_format={"type": "json_object"}, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.0)
        return json.loads(response.choices[0].message.content).get("type", "General")
    except Exception: 
        return "General"

def _fetch_and_analyze_searchcans_data(domain: str) -> dict | None:
    """
    Calls the SearchCans API, then performs local analysis, including detailed
    link categorization and counting. This version includes a fallback mechanism
    to parse links from raw HTML if the API doesn't provide a pre-parsed list.
    """
    # --- 1. API Call Configuration ---
    USER_KEY = "vcans_1767671917_da36a8f9-9020-4e99-8df5-d703938fc30a"
    API_URL = "https://www.searchcans.com/api/url"
    
    headers = {"Authorization": f"Bearer {USER_KEY}", "Content-Type": "application/json"}
    payload = {"s": f"https://{domain}", "t": "url", "w": 3000, "d": 30000, "b": True}

    try:
        # --- 2. Call the API ---
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60 )
        response.raise_for_status()
        api_result = response.json()

        if api_result.get("code") != 0:
            print(f"SearchCans API returned an error for {domain}: {api_result.get('msg')}")
            return None

        # --- 3. Extract Content from API Response ---
        data = api_result.get("data", {})
        if isinstance(data, str):
            try: data = json.loads(data)
            except json.JSONDecodeError: data = {"markdown": data, "html": ""}
        
        html = data.get("html", "")
        markdown = data.get("markdown", "")
        
        if not html:
            return None

        # --- 4. Perform Local Analysis on HTML and Markdown ---
        images_count = len(re.findall(r'<img\s', html, re.IGNORECASE))
        scripts_count = len(re.findall(r'<script', html, re.IGNORECASE))
        styles_count = len(re.findall(r'<style', html, re.IGNORECASE)) + \
                       len(re.findall(r'<link[^>]+rel=["\']?stylesheet', html, re.IGNORECASE))
        
        h1 = len(re.findall(r'<h1', html, re.IGNORECASE))
        h2 = len(re.findall(r'<h2', html, re.IGNORECASE))
        h3 = len(re.findall(r'<h3', html, re.IGNORECASE))
        total_headings = len(re.findall(r'<h[1-6]', html, re.IGNORECASE))
        headings_str = f"Total: {total_headings} (H1: {h1}, H2: {h2}, H3: {h3})"
        
        metadata_count = len(re.findall(r'<meta\s', html, re.IGNORECASE))
        word_count = len(markdown.split()) if markdown else 0
        content_length = len(html)

        # --- 5. Link Categorization and Counting Logic (ROBUST VERSION) ---
        internal_links_count = 0
        external_links_count = 0
        anchor_links_count = 0
        
        links_to_process = []
        
        # A. Primary Method: Use the pre-parsed list from SearchCans API if available
        links_json = data.get("links", [])
        if links_json and isinstance(links_json, list):
            links_to_process = [link.get('href') for link in links_json if link.get('href')]
            print(f"INFO for {domain}: Using pre-parsed links from SearchCans API. Found {len(links_to_process)} links.")

        # B. Fallback Method: If API provides no links, parse from raw HTML
        if not links_to_process:
            print(f"WARNING for {domain}: SearchCans API did not provide a 'links' array. Falling back to manual HTML parsing.")
            try:
                soup = BeautifulSoup(html, 'html.parser')
                links_to_process = [a['href'] for a in soup.find_all('a', href=True)]
            except Exception as e:
                print(f"ERROR for {domain}: Failed to parse HTML with BeautifulSoup: {e}")
                links_to_process = []

        # C. Process the definitive list of links
        if links_to_process:
            clean_domain = tldextract.extract(domain).registered_domain
            
            for href in links_to_process:
                if not href: continue

                if href.startswith('#'):
                    anchor_links_count += 1
                elif href.startswith(('mailto:', 'tel:', 'javascript:')):
                    pass 
                else:
                    try:
                        link_domain_info = tldextract.extract(href)
                        if not link_domain_info.registered_domain or link_domain_info.registered_domain == clean_domain:
                            internal_links_count += 1
                        else:
                            external_links_count += 1
                    except (ValueError, TypeError):
                        if href.startswith('/'):
                            internal_links_count += 1
        
        # --- 6. Return a single, comprehensive dictionary ---
        return {
            "raw_html": html, "markdown_content": markdown, "word_count": word_count,
            "content_length": content_length, "headings": headings_str, "images_count": images_count,
            "scripts_count": scripts_count, "styles_count": styles_count, "metadata_count": metadata_count,
            "internal_links_count": internal_links_count, "external_links_count": external_links_count,
            "anchor_links_count": anchor_links_count, "images_json": data.get("images"),
        }

    except Exception as e:
        print(f"An unexpected error occurred in _fetch_and_analyze_searchcans_data for {domain}: {e}")
        return None

def _extract_telegram_from_html(html_content: str) -> str:
    """
    Finds the first Telegram link (t.me) within the given HTML content using regex.
    Returns the link or 'N/A' if not found.
    """
    if not html_content:
        return "N/A"
    
    # Regex to find t.me links. It's flexible enough to catch variations.
    # It captures the full link like 't.me/username' or 't.me/joinchat/...'
    telegram_pattern = r'(?:https?:// )?(t\.me/[\w\d_]+(?:/)?[\w\d_]*)'
    
    match = re.search(telegram_pattern, html_content, re.IGNORECASE)
    
    if match:
        # Return the full matched link (e.g., "t.me/example_user")
        return match.group(1)
        
    return "N/A"

def _scan_domain_worker(domain: str) -> dict | None:
    """
    The main worker function to process a single domain. It orchestrates the entire
    scanning process, from initial checks to deep analysis for "Money Sites",
    and prepares the final data dictionary for the database.
    """
    # --- 1. Initialize all variables for the final database record ---
    # This ensures that every field exists, even if the scan is skipped or fails.
    domain_type = "N/A"
    language = "N/A"
    contact_info = "N/A"
    initial_http_status = "N/A"
    summary = ""

    # Content metrics from SearchCans (default to 0 or None )
    word_count = 0
    headings = None
    markdown_content = None
    images_count = 0
    scripts_count = 0
    styles_count = 0
    metadata_count = 0
    content_length = 0
    images_json = None
    internal_links_count = 0
    external_links_count = 0
    anchor_links_count = 0

    # Technical metrics from other APIs (default to 0 or None)
    website_total_path = 0
    mobile_perf_score = 0
    desktop_perf_score = 0
    whois_creation_date = None
    wayback_first_seen = None

    try:
        # --- 2. Perform initial, low-cost checks ---
        clean_root = tldextract.extract(domain).registered_domain
        initial_http_status = _get_initial_http_status(domain )

        # Early exit for Shell domains (.gov, .edu) to save resources
        if '.gov' in clean_root.lower() or '.edu' in clean_root.lower():
            return {
                'domain': domain, 'type': 'Shell', 'language': 'N/A', 'contact_info': 'N/A',
                'initial_http_status': initial_http_status, 'word_count': 0, 'website_total_path': 0,
                'performance_score_mobile': 0, 'performance_score_desktop': 0, 'whois_creation_date': None,
                'wayback_first_seen': None, 'headings': None, 'markdown_content': None, 'images_count': 0,
                'scripts_count': 0, 'styles_count': 0, 'metadata_count': 0, 'content_length': 0,
                'images': None, 'internal_links_count': 0, 'external_links_count': 0, 'anchor_links_count': 0,
                'summary': f"✔️ SUCCESS (SHELL ): {domain}"
            }

        # Check if the domain is already marked as a "Money Site" in the DB
        is_already_money_site = False
        try:
            existing_check = supabase.table('unique_domains').select('type').eq('domain', domain).execute()
            if existing_check.data and existing_check.data[0].get('type') == 'Money Site':
                is_already_money_site = True
        except Exception:
            pass

        # --- 3. Use SearchCans API as the primary data source for content ---
        analysis_data = _fetch_and_analyze_searchcans_data(domain)

        if not analysis_data:
            domain_type = 'Unreachable'
            summary = f"❌ FAILURE: {domain} | Type: Unreachable (SearchCans API failed or returned no content)"
        else:
            # --- 4. We have content, now perform AI classification ---
            markdown_for_ai = analysis_data.get("markdown_content", "")
            domain_type = analyze_domain_type_with_ai(domain, markdown_for_ai)

            # --- 5. Decide if a full, deep scan is required ---
            should_run_full_scan = (domain_type.strip().lower() == 'money site' or is_already_money_site)

            if should_run_full_scan:
                if is_already_money_site and domain_type != 'Unreachable':
                    domain_type = 'Money Site' # Ensure type is correctly set

                # --- A. Populate all content metrics from the SearchCans analysis ---
                word_count = analysis_data.get("word_count", 0)
                markdown_content = analysis_data.get("markdown_content")
                headings = analysis_data.get("headings")
                images_count = analysis_data.get("images_count", 0)
                scripts_count = analysis_data.get("scripts_count", 0)
                styles_count = analysis_data.get("styles_count", 0)
                metadata_count = analysis_data.get("metadata_count", 0)
                content_length = analysis_data.get("content_length", 0)
                images_json = analysis_data.get("images_json")
                internal_links_count = analysis_data.get("internal_links_count", 0)
                external_links_count = analysis_data.get("external_links_count", 0)
                anchor_links_count = analysis_data.get("anchor_links_count", 0)

                # --- B. Extract contact info and language from the same SearchCans data ---
                raw_html_from_api = analysis_data.get("raw_html", "")
                contact_info = _extract_telegram_from_html(raw_html_from_api)

                if markdown_content and len(markdown_content.split()) > 5:
                    try:
                        language = detect(markdown_content)
                    except LangDetectException:
                        language = "N/A"

                # --- C. Fetch remaining technical metrics from other external APIs ---
                website_total_path = get_sitemap_path_count(clean_root)
                mobile_perf_score, desktop_perf_score = get_website_speed(clean_root)
                whois_creation_date, wayback_first_seen = _fetch_whois_data(clean_root), _fetch_wayback_data(clean_root)
                
                summary = f"✔️ SUCCESS (MONEY SITE FULL SCAN): {domain} | All metrics updated."
            else:
                # If not a money site, we just record the type and skip the deep scan
                summary = f"✔️ SUCCESS (SKIPPED DEEP SCAN): {domain} | Type: {domain_type}"

        # --- 6. Assemble the final dictionary for Supabase upsert ---
        # This dictionary structure must exactly match the Supabase table columns.
        result_data = {
            'domain': domain,
            'type': domain_type,
            'language': language,
            'contact_info': contact_info,
            'initial_http_status': initial_http_status,
            'word_count': word_count,
            'website_total_path': website_total_path,
            'performance_score_mobile': mobile_perf_score,
            'performance_score_desktop': desktop_perf_score,
            'whois_creation_date': whois_creation_date,
            'wayback_first_seen': wayback_first_seen,
            'headings': headings,
            'markdown_content': markdown_content,
            'images_count': images_count,
            'scripts_count': scripts_count,
            'styles_count': styles_count,
            'metadata_count': metadata_count,
            'content_length': content_length,
            'images': images_json,
            'internal_links_count': internal_links_count,
            'external_links_count': external_links_count,
            'anchor_links_count': anchor_links_count,
            'summary': summary
        }
        return result_data

    except Exception as e:
        # Global error handler for any unexpected issues within the worker
        return {
            'domain': domain,
            'error': str(e ),
            'summary': f"🚨 CRITICAL WORKER ERROR for {domain}: {e}"
        }


# //======================================================================//
# //======= PRIMARY SCANNER LOOP (UI DETAILS OPTIMIZED) ==================//
# //======================================================================//

def run_ai_scan_and_update(domains_to_scan, progress_bar, current_status_container, last_result_container):
    total_domains = len(domains_to_scan)
    success_count = 0
    MAX_WORKERS = 10 # Concurrency setting
    
    # 1. Initialization and Concurrency Info
    current_status_container.info(f"🚀 Starting parallel scan for {total_domains} domains. Concurrency: **{MAX_WORKERS} workers**.")
    last_result_container.empty()
    
    futures = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        
        # 2. Task Submission Phase
        current_status_container.info(f"🔄 Submitting **{total_domains}** tasks to the worker pool...")
        for domain in domains_to_scan:
            future = executor.submit(_scan_domain_worker, domain)
            futures[future] = domain 

        current_status_container.success(f"✅ All {total_domains} tasks submitted. Awaiting results...")

        # 3. Result Processing Phase (Iterate over completed tasks)
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            domain = futures[future]
            
            # Progress Bar Update: Show current progress and the just completed domain
            progress_bar.progress(
                (i + 1) / total_domains, 
                text=f"Progress: {i + 1}/{total_domains} | Just Completed: **{domain}**"
            )
            
            try:
                result_data = future.result()
            except Exception as e:
                result_data = {'domain': domain, 'error': f"🚨 CRITICAL ERROR during execution: {e}", 'summary': f"🚨 CRITICAL ERROR for {domain}: {e}"}

            if 'error' in result_data:
                # Error Handling and UI Feedback
                last_result_container.error(result_data['summary'])
                current_status_container.error(f"❌ Failed to process: **{domain}**. Check Last Result for details.")
            else:
                summary = result_data.pop('summary') 
                
                domain_type = result_data.get('type', 'N/A')
                word_count = result_data.get('word_count', 0)
                
                # Detailed Success Feedback (including key metrics)
                last_result_container.success(summary)
                current_status_container.success(
                    f"✅ Finished: **{domain}** | Type: **{domain_type}** | Words: **{word_count}** | DB Status: Updating..."
                )
                
                # Database Update
                supabase.table('unique_domains').upsert(result_data).execute()

                success_count += 1
                
            time.sleep(0.1) 

    # 4. Finalization
    current_status_container.success(f"🏁 Scan finished. Processed {success_count} domains."); st.balloons()
    st.session_state.scan_in_progress = False; time.sleep(5)

# //======================================================================//
# //======= DATA INTEGRITY CHECK FUNCTION ================================//
# //======================================================================//

def run_data_integrity_check(df: pd.DataFrame):
    """Checks for rank duplication within the loaded DataFrame."""
    if df.empty:
        st.error("Cannot perform check: No SERP ranking data found within the current date range. Please adjust the date filter.")
        return

    # Define unique constraint columns: The same search (date/keyword/device/interface) should not have duplicate rankings.
    ranking_integrity_cols = ['date', 'keyword', 'device', 'interface', 'ranking']
    
    # Find all duplicate rows (keep=False ensures both/all conflicting records are included)
    duplicate_ranks = df[df.duplicated(subset=ranking_integrity_cols, keep=False)]
    
    if not duplicate_ranks.empty:
        st.error(f"🚨 **{len(duplicate_ranks)}** Data Integrity Conflicts Found!")
        st.markdown("---")
        st.subheader("Conflict Details (Overlapping Ranking Conflicts)")
        st.warning("Duplicate rankings found for the same search query (i.e., different domains occupying the same rank position).")
        
        # Display the conflicting DataFrame, sorted by conflict columns for easy viewing
        st.dataframe(duplicate_ranks.sort_values(by=ranking_integrity_cols), use_container_width=True)
        
        # Option to download the conflicting data
        csv_data = duplicate_ranks.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Conflict Data CSV",
            data=csv_data,
            file_name='serp_ranking_integrity_conflicts.csv',
            mime='text/csv'
        )
    else:
        st.success("✅ Data Integrity Check passed! No duplicate ranking conflicts found in the displayed SERP data.")


# //======================================================================//
# //======= UI CODE (COMPLETE & FIXED) ===================================//
# //======================================================================//

st.set_page_config(layout="wide")

# --- SESSION STATE INITIALIZATION (Full Version) ---
# This ensures all necessary session variables are set on the first run.
if 'scan_in_progress' not in st.session_state:
    st.session_state.scan_in_progress = False
if 'integrity_check_triggered' not in st.session_state:
    st.session_state.integrity_check_triggered = False
if 'delete_stage' not in st.session_state:
    st.session_state.delete_stage = 0
if 'filter_start_date' not in st.session_state:
    st.session_state.filter_start_date = ABS_MAX_DATE - timedelta(days=7)
if 'filter_end_date' not in st.session_state:
    st.session_state.filter_end_date = ABS_MAX_DATE
if 'debug_domain' not in st.session_state:
    st.session_state.debug_domain = None
if 'debug_types' not in st.session_state:
    st.session_state.debug_types = []


# --- SIDEBAR: The Control Panel for All Actions ---
with st.sidebar:
    st.title("⚙️ Control Panel")
    st.markdown("---")

    # === 1. Core Data Actions ===
    st.header("Core Data Actions")

    if st.button("🚀 Update SERP Ranking", disabled=bool(st.session_state.scan_in_progress), help="Fetches the latest keyword ranking data from keyword.com API."):
        run_api_importer()

    if st.button("🕵️ Check Data Integrity", disabled=bool(st.session_state.scan_in_progress), help="Scans the database for duplicate ranking entries."):
        st.warning("Data Integrity Check is currently disabled in this view.") # As the main display is removed.

    st.markdown("---")

    # === 2. AI Analysis Actions ===
    st.header("AI Analysis")

    scan_ui_placeholder = st.empty()
    if not st.session_state.scan_in_progress:
        if scan_ui_placeholder.button("✨ Run Full AI Scan", help="Scans all domains that have not been analyzed yet."):
            st.session_state.scan_in_progress = "full_scan"
            st.rerun()

    # Container for scan progress UI, which appears when a scan is active
    if st.session_state.scan_in_progress:
        with scan_ui_placeholder.container():
            progress_bar = st.progress(0, text="Initializing Scan...")
            st.write("Current Progress:")
            current_status_container = st.empty()
            st.write("Last Result:")
            last_result_container = st.empty()
            domains_to_scan = []

            # --- Domain Queue Building Logic ---
            if st.session_state.scan_in_progress == "full_scan":
                current_status_container.info("🔄 Syncing and queuing unscanned domains...")
                try:
                    # Sync new domains from serp_rankings to unique_domains
                    cutoff_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
                    serp_resp = supabase.table('serp_rankings').select('domain').gte('date', cutoff_date).execute()
                    if serp_resp.data:
                        serp_domains = {r['domain'] for r in serp_resp.data if r['domain']}
                        unique_resp = supabase.table('unique_domains').select('domain').execute()
                        existing_domains = {r['domain'] for r in unique_resp.data} if unique_resp.data else set()
                        new_domains_to_add = list(serp_domains - existing_domains)
                        if new_domains_to_add:
                            current_status_container.info(f"📥 Found {len(new_domains_to_add)} new domains. Adding to queue...")
                            supabase.table('unique_domains').insert([{'domain': d} for d in new_domains_to_add]).execute()
                            current_status_container.success("✅ Domain list synced.")
                        else:
                            current_status_container.info("✅ Domain list is up to date.")
                except Exception as e:
                    current_status_container.warning(f"⚠️ Sync step issue: {e}")

                # Fetch domains where type is None for the full scan
                response = supabase.table('unique_domains').select('domain').is_('type', None).execute()
                if response.data:
                    domains_to_scan = [rec['domain'] for rec in response.data]
                else:
                    st.success("All domains are fully analyzed.")
                    st.session_state.scan_in_progress = False
                    time.sleep(3)
                    st.rerun()

            elif st.session_state.scan_in_progress == "debug_scan":
                if st.session_state.debug_domain:
                    domains_to_scan = [st.session_state.debug_domain]
                elif st.session_state.debug_types:
                    query = supabase.table('unique_domains').select('domain')
                    types_to_fetch = [t for t in st.session_state.debug_types if t != 'None']
                    is_none_requested = 'None' in st.session_state.debug_types

                    fetched_domains = []
                    if types_to_fetch:
                        resp = query.in_('type', types_to_fetch).execute()
                        if resp.data: fetched_domains.extend([r['domain'] for r in resp.data])
                    if is_none_requested:
                        resp = supabase.table('unique_domains').select('domain').is_('type', None).execute()
                        if resp.data: fetched_domains.extend([r['domain'] for r in resp.data])
                    
                    domains_to_scan = list(set(fetched_domains)) # Remove duplicates

                if domains_to_scan:
                    current_status_container.info(f"🔍 Found {len(domains_to_scan)} domains for debug scan.")
                else:
                    st.warning("No domains found for the selected debug criteria.")
                    st.session_state.scan_in_progress = False
                    time.sleep(3)
                    st.rerun()

            # --- Execute Scan ---
            if domains_to_scan:
                run_ai_scan_and_update(domains_to_scan, progress_bar, current_status_container, last_result_container)
                st.rerun()

    st.markdown("---")

    # === 3. Debug Mode ===
    st.header("Debug Mode")
    st.write("Re-scan specific domains for debugging purposes.")

    try:
        type_resp = supabase.table('unique_domains').select('type').execute()
        all_types = {'None', 'Unreachable', 'General', 'Money Site', 'Review Site', 'Shell'}
        if type_resp.data:
            db_types = {str(d['type']) for d in type_resp.data if d['type'] is not None}
            all_types.update(db_types)
        selected_types = st.multiselect(
            "Filter by Type for Debug Scan",
            options=sorted(list(all_types)),
            default=[],
            disabled=bool(st.session_state.scan_in_progress)
        )
    except Exception:
        selected_types = st.multiselect("Filter by Type", options=['Error loading types'], disabled=True)

    debug_domain_input = st.text_input("OR Scan a Single Domain", placeholder="example.com", disabled=bool(st.session_state.scan_in_progress))

    if st.button("🔬 Debug Scan Selected", disabled=bool(st.session_state.scan_in_progress) or (not selected_types and not debug_domain_input)):
        st.session_state.scan_in_progress = "debug_scan"
        st.session_state.debug_domain = debug_domain_input if debug_domain_input else None
        st.session_state.debug_types = selected_types if selected_types else []
        st.rerun()

    st.markdown("---")

    # === 4. Danger Zone ===
    st.header("Danger Zone")
    start_date_delete = st.date_input("Deletion Start Date", key='filter_start_date')
    end_date_delete = st.date_input("Deletion End Date", key='filter_end_date')

    if st.session_state.delete_stage == 0:
        if st.button("💣 Delete SERP Data by Range", disabled=bool(st.session_state.scan_in_progress)):
            st.session_state.delete_stage = 1
            st.rerun()
    elif st.session_state.delete_stage == 1:
        st.warning(f"⚠️ Confirm deletion of SERP data from {start_date_delete} to {end_date_delete}?")
        c1, c2 = st.columns(2)
        if c1.button("✅ YES, DELETE", use_container_width=True):
            delete_serp_data_by_date_range(start_date_delete, end_date_delete)
            st.session_state.delete_stage = 0
            st.rerun()
        if c2.button("❌ NO, CANCEL", use_container_width=True):
            st.session_state.delete_stage = 0
            st.rerun()


# //======================================================================//
# //======= MAIN PAGE CONTENT (NEW OVERVIEW VERSION) =====================//
# //======================================================================//

st.title("📊 SERP & AI Analysis Dashboard")
st.write(
    "这是一个强大的数据处理工具，用于自动获取 SERP 排名、分析竞争对手网站，并利用 AI 和多种 API 获取深度指标。"
)
st.markdown("---")

st.header("🚀 功能核心：AI 驱动的网站深度扫描")
st.info(
    """
    当您在侧边栏启动 **AI 分析**后，系统会对数据库中的域名（特别是被识别为 **"Money Site"** 的域名）执行一次全面的深度扫描。
    以下是系统在完整扫描期间会抓取的所有指标及其来源。
    """
)

# --- Create two columns for better layout ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("内容与结构指标")
    st.markdown(
        """
        这些指标主要由 **SearchCans API** 提供原始数据，再通过**本地脚本分析**提取，专注于分析页面的内容丰富度和结构。
        """
    )
    st.markdown(
        """
        | 指标 (Metric) | 提供者 / 来源 |
        | :--- | :--- |
        | **markdown_content** | **SearchCans API** |
        | **word_count** | 本地分析 (from Markdown) |
        | **content len (chars)** | 本地分析 (from HTML) |
        | **headings (H1-H6)** | 本地分析 (from HTML) |
        | **images** | 本地分析 (from HTML) |
        | **links** | 本地分析 (from HTML) |
        | **scripts** | 本地分析 (from HTML) |
        | **styles** | 本地分析 (from HTML) |
        | **metadata** | 本地分析 (from HTML) |
        | **images (JSON)** | **SearchCans API** |
        | **页面内部链接数** | 本地分析 (from Links JSON) |
        """
    )

with col2:
    st.subheader("技术、性能与历史指标")
    st.markdown(
        """
        这些指标来自多个专业的第三方 API，用于评估网站的技术健康度、性能和历史资历。
        """
    )
    st.markdown(
        """
        | 指标 (Metric) | 提供者 / 来源 |
        | :--- | :--- |
        | **performance_score_desktop** | **Google PageSpeed API** |
        | **performance_score_mobile** | **Google PageSpeed API** |
        | **domain_age** | **DomainGuru API** |
        | **wayback** | **Wayback Machine API** |
        | **sitemap_path** | 直接网站抓取 (Requests) |
        | **initial_http_status** | 直接网站抓取 (Requests) |
        | **contact_info**| **本地分析 (from SearchCans HTML)** |
        """
    )

st.markdown("---")

st.subheader("智能分类与元数据")
st.markdown(
    """
    在进行深度扫描之前，系统会首先对网站进行智能分类，以决定后续的操作。
    """
)
st.markdown(
    """
    | 指标 (Metric) | 提供者 / 来源 | 详细说明 |
    | :--- | :--- | :--- |
    | **type** | **AI (OpenAI GPT-4o) & 内部规则** | 核心分类指标，判断网站是否为 "Money Site", "Review Site", "Shell" 等。 |
    | **language** | **`langdetect` 库 (本地分析)** | 基于 SearchCans 返回的 Markdown 内容，判断页面主要语言。 |
    """
)

st.markdown("---")
st.success("您可以通过侧边栏的 **Control Panel** 来启动数据更新和 AI 分析任务。")