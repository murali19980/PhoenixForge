import sys
import json
import os
import requests
import time
import urllib.parse
import difflib
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from duckduckgo_search import DDGS
import psutil
from llm_router import ask_llm_json, CONFIG

# Configure logger for this module
logger = logging.getLogger("phoenixforge.engine")

MEMORY_FILE = "memory.jsonl"

def system_audit():
    ram = psutil.virtual_memory().total / (1024**3)
    try:
        import subprocess
        vram = int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.total','--format=csv,noheader,nounits'], encoding='utf-8').split('\n')[0]) / 1024
    except:
        vram = 0
    logger.info(f"[System] RAM: {ram:.1f}GB, VRAM: {vram:.1f}GB")
    return {"ram": ram, "vram": vram}

def load_jina_config():
    """Loads Jina API config from config.json or environment."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("JINA_API_KEY")
    timeout = 15
    try:
        from llm_router import CONFIG
        jina_conf = CONFIG.get("jina", {})
        if not api_key:
            api_key = jina_conf.get("api_key")
        timeout = jina_conf.get("timeout", 15)
    except Exception:
        pass
    return api_key, timeout

# Curated high-quality post-mortem sources that always exist and load well
_CURATED_POSTMORTEM_URLS = [
    "https://niteo.co/blog/failed-saas-project",
    "https://elliotbonneville.com/blog/validate-your-pricing-model-like-i-didnt/",
    "https://mmartinfahy.medium.com/my-experience-releasing-3-failed-saas-products-e2b4e7d5bc7c",
    "https://www.cbinsights.com/research/startup-failure-post-mortem/",
    "https://medium.com/@SoldOutSupplier/my-startup-failed-i-lost-everything-ee3b50e1b6d4",
    "https://www.failory.com/blog/startup-failure-reasons",
    "https://www.indiehackers.com/post/my-product-failed-lessons-learned-after-2-years",
]

def search_web(idea: str, max_results=10) -> list:
    """
    Search for relevant failure post-mortems using:
    1. HackerNews Algolia API — searches by idea keywords, then broader category queries
    2. DuckDuckGo (fallback, often rate-limited)
    3. Curated post-mortem URLs as guaranteed fallback
    """
    from urllib.parse import urlparse, quote_plus
    
    # Specific queries for the idea
    specific_queries = [
        f"{idea} failure post mortem",
        f"{idea} why failed",
        f"{idea} startup shut down",
    ]
    
    # Broader queries that always return HN results
    broad_queries = [
        "startup failure post mortem lessons",
        "SaaS failed why we shut down",
        "product failure postmortem UX cost",
    ]
    
    urls = []
    ignored_domains = ['duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com',
                       'youtube.com', 'instagram.com', 'twitter.com', 'x.com',
                       'facebook.com', 'linkedin.com', 'news.ycombinator.com']
    
    def is_valid_url(u):
        try:
            parsed = urlparse(u)
            domain = parsed.netloc.lower()
            if not parsed.scheme.startswith('http'):
                return False
            return not any(bad in domain for bad in ignored_domains)
        except Exception:
            return False
    
    # ── Strategy 1: HackerNews Algolia — specific idea queries ────────────────
    headers_hn = {'User-Agent': 'PhoenixForge/3.0 (research-tool)'}
    for q in specific_queries:
        try:
            search_url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(q)}&hitsPerPage=5"
            logger.info(f"[HN Search] Querying: {q}")
            resp = requests.get(search_url, headers=headers_hn, timeout=8)
            if resp.status_code == 200:
                hits = resp.json().get('hits', [])
                for hit in hits:
                    story_url = hit.get('url')
                    if story_url and is_valid_url(story_url) and story_url not in urls:
                        urls.append(story_url)
                logger.info(f"  [HN] Got {len(hits)} stories, {sum(1 for h in hits if h.get('url'))} with URLs")
        except Exception as e:
            logger.warning(f"[HN Search] Failed for '{q}': {e}")
    
    # ── Strategy 2: HackerNews Algolia — broader category queries ─────────────
    if len(urls) < 3:
        logger.info("[Search] Specific HN results sparse — broadening to SaaS/startup failure queries")
        for q in broad_queries:
            try:
                search_url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(q)}&hitsPerPage=4"
                resp = requests.get(search_url, headers=headers_hn, timeout=8)
                if resp.status_code == 200:
                    hits = resp.json().get('hits', [])
                    for hit in hits:
                        story_url = hit.get('url')
                        if story_url and is_valid_url(story_url) and story_url not in urls:
                            urls.append(story_url)
                    logger.info(f"  [HN Broad] Got {len(hits)} stories for '{q}'")
            except Exception as e:
                logger.warning(f"[HN Broad] Failed for '{q}': {e}")
    
    # ── Strategy 3: DuckDuckGo (last resort, often rate-limited) ──────────────
    if len(urls) < 4:
        logger.info("[Search] HN results sparse. Trying DuckDuckGo...")
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for q in specific_queries[:2]:
                    try:
                        results = list(ddgs.text(q, max_results=3))
                        for r in results:
                            href = r.get('href')
                            if href and is_valid_url(href) and href not in urls:
                                urls.append(href)
                    except Exception as e:
                        logger.warning(f"[DDG Search] Failed for '{q}': {e}")
        except Exception as e:
            logger.error(f"[DDG Search] Init failed: {e}")
    
    # ── Strategy 4: Curated fallback post-mortems (always available) ──────────
    if len(urls) < 4:
        logger.info("[Search] Adding curated post-mortem fallback URLs for context")
        for curated_url in _CURATED_POSTMORTEM_URLS:
            if curated_url not in urls:
                urls.append(curated_url)
                if len(urls) >= max_results:
                    break
    
    result = list(dict.fromkeys(urls))[:max_results]
    logger.info(f"[Search] Total unique URLs collected: {len(result)}")
    return result

def extract_with_jina(url: str, api_key: str = None, timeout: int = 30) -> str:
    """
    Scrapes the URL using Jina AI Reader API (https://r.jina.ai/{url}).
    Falls back to requests + BeautifulSoup if it fails.
    """
    import requests
    from bs4 import BeautifulSoup
    import random
    
    jina_url = f"https://r.jina.ai/{url}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    logger.info(f"[Jina Reader] Extracting: {url}")
    try:
        response = requests.get(jina_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            content = response.text
            # Filter out Jina error responses (404, 429, etc.)
            error_indicators = ['Warning: Target URL returned error', 'Not Found', 'Too Many Requests']
            is_error_response = any(ind in content for ind in error_indicators) and len(content) < 400
            if content and len(content.strip()) > 200 and not is_error_response:
                logger.info(f"  [Success] Extracted {len(content)} chars from Jina Reader")
                return content
            elif is_error_response:
                logger.warning(f"  [Warning] Jina Reader returned an error page for {url}")
            else:
                logger.warning(f"  [Warning] Received short content from Jina Reader for {url}")
        else:
            logger.warning(f"  [Warning] Jina Reader returned status code {response.status_code} for {url}")
    except Exception as e:
        logger.warning(f"  [Warning] Jina Reader request failed for {url}: {e}")
        
    # Fallback to requests + BeautifulSoup
    logger.info(f"[Scraper Fallback] Scraping {url} with BeautifulSoup")
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
    ]
    headers = {'User-Agent': random.choice(user_agents)}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            lines = (line.strip() for line in soup.get_text().splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            if len(text) > 100:
                logger.info(f"  [Success] Extracted {len(text)} chars (BS4 fallback)")
                return text[:5000]
    except Exception as e:
        logger.error(f"  [Error] BS4 fallback failed for {url}: {e}")
        
    return ""


def deep_research_gather(idea, task_id=None, active_tasks_dict=None, queries=None):
    import time
    from urllib.parse import urlparse
    
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["current_step"] = "Searching the web for failure signals..."
        active_tasks_dict[task_id]["message"] = "Querying search engines..."
        
    urls = search_web(idea, max_results=10)
    
    if not urls:
        logger.warning("[Scraper] No search results found at all.")
        return {
            "urls": [],
            "combined_text": "No real URLs could be retrieved. Check your internet connection or try again later.",
            "raw_combined_markdown": "No real URLs could be retrieved. Check your internet connection or try again later.",
            "source_count": 0
        }
        
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["total_articles"] = len(urls)
        active_tasks_dict[task_id]["current_step"] = f"Found {len(urls)} target URLs."
        active_tasks_dict[task_id]["message"] = f"Extracting content from {len(urls)} targets..."
        
    logger.info(f"[Scraper] Deduplicated target URLs ({len(urls)}): {urls}")
    
    jina_key, timeout = load_jina_config()
    
    scraped_data = {}
    for idx, url in enumerate(urls):
        netloc = urlparse(url).netloc
        if active_tasks_dict and task_id:
            active_tasks_dict[task_id]["current_step"] = f"Scraping {idx+1}/{len(urls)}: {netloc}"
            active_tasks_dict[task_id]["message"] = "Extracting article body..."
            
        content = extract_with_jina(url, api_key=jina_key, timeout=timeout)
        if content and len(content.strip()) > 100:
            scraped_data[url] = content[:5000] # Truncate each page to 5000 chars
            if active_tasks_dict and task_id:
                active_tasks_dict[task_id]["extracted_count"] += 1
                
    if scraped_data:
        combined_text_lines = []
        for i, (url, text) in enumerate(scraped_data.items()):
            combined_text_lines.append(f"=== SOURCE {i+1} ===")
            combined_text_lines.append(f"URL: {url}")
            combined_text_lines.append(f"Text:\n{text}")
            combined_text_lines.append("\n")
            
        combined_text = "\n".join(combined_text_lines)
        
        words = combined_text.split()
        if len(words) > 8000:
            logger.info(f"[Scraper] Truncating combined text from {len(words)} to 8000 words...")
            combined_text = " ".join(words[:8000])
            
        with open("raw_data.txt", "w", encoding="utf-8") as f:
            f.write(combined_text)
            
        return {
            "urls": list(scraped_data.keys()),
            "combined_text": combined_text,
            "raw_combined_markdown": combined_text,
            "source_count": len(scraped_data),
            "scraped_data": scraped_data
        }
    else:
        logger.warning("[Scraper] No web data scraped successfully.")
        return {
            "urls": [],
            "combined_text": "No real URLs could be retrieved. Check your internet connection or try again later.",
            "raw_combined_markdown": "No real URLs could be retrieved. Check your internet connection or try again later.",
            "source_count": 0,
            "scraped_data": {}
        }

def generate_mermaid_flowchart(idea, failures):
    """Generates a Mermaid flowchart showing the user journey and failure points."""
    mermaid = f"```mermaid\ngraph TD\n    A[User starts using {idea[:20]}] --> B{{Is onboarding easy?}}\n    B -->|No| C[❌ UX Failure: Users churn]\n    B -->|Yes| D[User engages with core feature]\n    D --> E{{Is backend stable?}}\n    E -->|No| F[❌ Tech Failure: Bugs/crashes]\n    E -->|Yes| G{{Does it cost too much to run?}}\n    G -->|Yes| H[❌ Cost Failure: No profit margin]\n    G -->|No| I[✅ Potential Success Path]\n    C --> J[Analyze user feedback]\n    F --> J\n    H --> J\n    J --> K[Implement fixes]\n"
    for f in failures[:3]:
        clean_issue = f['issue'].replace('"', "'").replace('(', '').replace(')', '').split(":")[0]
        mermaid += f"    {f['category'][0]}Fail[\"{clean_issue[:30]}\"] --> J\n"
    mermaid += "```"
    return mermaid

def step_by_step_extractor(raw_text, idea, model=None):
    """Forces the LLM to act as a Project Coroner (Business/UX failure analyst)."""
    base_prompt = f"""
    You are a brutally honest Project Coroner. Your job is to autopsy why business ideas FAIL.
    
    Given the project idea: "{idea}"
    And the raw web scrapes:
    {raw_text[:8000]}
    
    Return ONLY raw JSON. Do not add code examples, do not give coding tutorials, do not suggest tech stacks.
    
    Here are 3 examples of excellent Coroner autopsies:

    Example 1 (Social Media Scheduler):
    - UX Risk: "80% churn by week 2. Users schedule 3 posts, get no engagement, and abandon the platform."
    - Market Risk: "APIs from LinkedIn/X rate-limit to 50 posts/day. Users hit limits and blame the product."
    - Cost Risk: "OpenAI API costs $0.02 per post. At 1000 users, that's $600/month before revenue."
    - Fixes: ["Add analytics dashboard to show engagement", "Pivot to enterprise scheduling", "Use local LLM to cut costs"]

    Example 2 (Fitness App):
    - UX Risk: "90% churn by day 7. Users stop logging food manually."
    - Market Risk: "MyFitnessPal has 80% market share. Switching costs are zero."
    - Cost Risk: "Apple Health API doesn't expose step data in real-time. Users get frustrated."
    - Fixes: ["Sync with wearables automatically", "Focus on gamification", "Partner with gyms for B2B"]

    Example 3 (AI Resume Builder):
    - UX Risk: "95% churn after first download. Users have zero reason to return."
    - Market Risk: "Recruiters instantly flag AI-generated prose. 70% of resumes get auto-rejected."
    - Cost Risk: "GPT-4 API costs $0.03 per resume. Users won't pay more than $10 once."
    - Fixes: ["Pivot to live career tracker", "Add human review layer", "White-label to universities"]

    Extract these 3 categories with extreme bluntness. You MUST cite specific phrases or patterns found in the raw web scrapes if available (e.g. "As seen in: '...'"):
    1. UX/Retention: Why do users quit forever?
    2. Market/B2B: Why do gatekeepers (recruiters, managers) hate it?
    3. Tech/Cost: What burns money or breaks scaling?
    
    Output exactly this JSON structure:
    {{
      "ux_risks": ["Specific cited risk 1", "Risk 2"],
      "market_risks": ["Specific cited gatekeeper rejection reason 1"],
      "cost_risks": ["Specific cited financial failure reason 1"],
      "fixes": [
         {{"title": "Pivot Strategy 1", "action": "Specific business pivot to survive"}},
         {{"title": "Pivot Strategy 2", "action": "Alternative market to target"}}
      ]
    }}
    
    Do not include anything else. No markdown, no explanations. Just the raw JSON.
    """
    logger.info("[Coroner] Running Project Coroner analysis...")
    return ask_llm_json(base_prompt, raw_text, model_override=model)

def calculate_quality_score(source_count, raw_text):
    import re
    if not raw_text or source_count == 0:
        return 0.0
    
    # 1. Source diversity (0.0 - 0.3)
    # Cap source count at 15
    diversity_score = min(source_count, 15) / 15.0 * 0.3
    
    # 2. Word count density (0.0 - 0.3)
    # Target is 2000 words
    word_count = len(raw_text.split())
    density_score = min(word_count, 2000) / 2000.0 * 0.3
    
    # 3. Metric extraction (0.0 - 0.4)
    # Regex for metrics: numbers followed by %, $, USD, users, requests, etc.
    metric_pattern = r'\b\d+(?:\.\d+)?\s*(?:%|\$|usd|users|requests|customers|clients|clicks|dollars|cents|minutes|seconds|hours|percent)\b'
    metrics_found = len(re.findall(metric_pattern, raw_text, re.IGNORECASE))
    metrics_score = min(metrics_found, 10) / 10.0 * 0.4
    
    total_score = diversity_score + density_score + metrics_score
    return round(total_score, 2)

def run_phoenixforge(idea, task_id=None, active_tasks_dict=None, queries=None, strategy_metadata=None, model=None):
    logger.info(f"[PhoenixForge] Scanning: {idea}")
    audit = system_audit()
    
    research_results = deep_research_gather(idea, task_id, active_tasks_dict, queries)
    raw_text = research_results["combined_text"]
    urls_scraped = research_results["urls"]
    source_count = research_results["source_count"]
    scraped_data = research_results.get("scraped_data", {})
    
    if strategy_metadata is None:
        strategy_metadata = {
            "queries_used": queries or [
                f'{idea} failure post mortem',
                f'{idea} horror story',
                f'{idea} shut down',
                f'{idea} abandoned'
            ],
            "scraper_type": "jina_ai_reader",
            "prompt_version": 1
        }
        
    quality_score = calculate_quality_score(source_count, raw_text)
    logger.info(f"[Coroner] Quality score calculated: {quality_score}")
    
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["current_step"] = "Analyzing signals using local LLM..."
        active_tasks_dict[task_id]["message"] = "Extracting UX, Tech, and Cost failure patterns..."
        
    if source_count == 0:
        gathered_str = "0 sources scraped"
        cleaned_str = "0 unique signals"
        cleaned_text = "⚠️ No real web pages could be fetched. Your analysis is based on zero live data."
    else:
        gathered_str = f"{source_count} sources scraped"
        cleaned_str = f"{source_count} unique signals"
        
        graveyard_lines = []
        for i, url in enumerate(urls_scraped):
            text = scraped_data.get(url, "")
            snippet = ""
            if text:
                clean_lines = [line.strip() for line in text.split('\n') if line.strip()]
                clean_text = " ".join(clean_lines)
                snippet = clean_text[:300].strip()
                if len(clean_text) > 300:
                    snippet += "..."
            if snippet:
                graveyard_lines.append(f"Source {i+1}: {url}\nExcerpt: {snippet}\n")
            else:
                graveyard_lines.append(f"Source {i+1}: {url}\n")
        cleaned_text = "\n".join(graveyard_lines)
    
    data = step_by_step_extractor(raw_text, idea, model=model)
    
    ux_risks = data.get('ux_risks', [])
    market_risks = data.get('market_risks', [])
    cost_risks = data.get('cost_risks', [])
    fixes_list = data.get('fixes', [])
    
    failures = []
    for r in cost_risks: failures.append({"issue": r, "category": "Cost"})
    for r in market_risks: failures.append({"issue": r, "category": "Tech"})
    for r in ux_risks: failures.append({"issue": r, "category": "UX"})
    for f in fixes_list:
        failures.append({"issue": f"{f.get('title', 'Pivot')}: {f.get('action', '')}", "category": "General"})
        
    if not failures: failures = [{"issue": "Generic Risk Detected", "category": "General"}]
    
    mermaid_flowchart = generate_mermaid_flowchart(idea, failures)
    
    pipeline_metadata = {
        "gathered": gathered_str,
        "cleaned": cleaned_str,
        "organized": f"{len(cost_risks) + len(market_risks) + len(ux_risks)} business risks identified",
        "presented": "Report compiled successfully"
    }
    
    report = f"# 🐦🔥 PhoenixForge Report: {idea}\n\n## Risk Heatmap\n{json.dumps({'Cost': len(cost_risks), 'Tech': len(market_risks), 'UX': len(ux_risks)}, indent=2)}\n\n{mermaid_flowchart}\n\n## 📉 The Graveyard\n{cleaned_text}\n\n## Actionable Fixes\n{json.dumps(failures, indent=2)}\n\n## Pipeline Metadata\n{json.dumps(pipeline_metadata, indent=2)}"
    with open("phoenixforge_report.md", "w", encoding='utf-8') as f: f.write(report)
    with open(MEMORY_FILE, "a", encoding='utf-8') as f: f.write(json.dumps({"idea": idea, "failures": failures, "date": str(datetime.now())}) + "\n")
    logger.info("[Report] Report saved to phoenixforge_report.md")
    
    # Save to SQLite history vault
    analysis_id = None
    try:
        import history
        analysis_id = history.save_analysis(
            idea=idea,
            full_scraped_text=raw_text,
            heatmap_dict={'Cost': len(cost_risks), 'Tech': len(market_risks), 'UX': len(ux_risks)},
            fixes_list=failures,
            graveyard_text=cleaned_text,
            raw_content=report,
            raw_combined_markdown=raw_text,
            scraped_urls=urls_scraped,
            source_count=source_count,
            strategy_metadata=strategy_metadata,
            quality_score=quality_score
        )
        logger.info(f"[History] Analysis successfully saved to SQLite history vault (phoenixforge.db), ID: {analysis_id}")
    except Exception as e:
        logger.error(f"[History] Failed to save to SQLite database: {e}")
        
    return {
        "status": "success",
        "id": analysis_id,
        "heatmap": {'Cost': len(cost_risks), 'Tech': len(market_risks), 'UX': len(ux_risks)},
        "fixes": failures,
        "graveyard": cleaned_text,
        "pipeline": pipeline_metadata,
        "raw_content": report,
        "quality_score": quality_score
    }

if __name__ == "__main__":
    run_phoenixforge(sys.argv[1] if len(sys.argv) > 1 else "AI Resume Builder")
