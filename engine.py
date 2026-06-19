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

def get_offline_fallback(idea: str) -> str:
    return (
        f"[⚠️ REAL-TIME RESEARCH UNAVAILABLE] All search engines are temporarily "
        f"blocked or rate-limited. Unable to perform real-time analysis for '{idea}'.\n\n"
        f"Please try again in a few minutes, or manually search these resources:\n"
        f"- https://www.failory.com/\n"
        f"- https://news.ycombinator.com/\n"
        f"- https://www.reddit.com/r/startups/\n"
        f"- https://www.cbinsights.com/research/startup-failure-reasons/"
    )

def search_for_urls(idea: str, queries=None):
    """
    Search DuckDuckGo (and Google as fallback) for relevant startup failure signals.
    """
    import random
    from urllib.parse import urlparse
    
    if not queries:
        queries = [
            f"{idea} failure post mortem",
            f"{idea} horror story",
            f"{idea} shut down",
            f"{idea} abandoned"
        ]
        
    logger.info(f"[Search] Executing search queries for: {idea}")
    urls = []
    
    # Try DuckDuckGo first
    try:
        from duckduckgo_search import DDGS
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        headers = {'User-Agent': random.choice(user_agents)}
        
        with DDGS(headers=headers) as ddgs:
            for q in queries:
                try:
                    logger.info(f"[DDG Search] Querying: {q}")
                    results = list(ddgs.text(q, max_results=3))
                    if results:
                        for r in results:
                            href = r.get('href')
                            if href and href not in urls:
                                urls.append(href)
                except Exception as ddg_single_err:
                    logger.warning(f"[DDG Search] Query failed for '{q}': {ddg_single_err}")
    except Exception as ddg_err:
        logger.error(f"[DDG Search] Failed to initialize DDGS: {ddg_err}")
        
    # If DDG returned fewer than 4 URLs, try Google as a fallback
    if len(urls) < 4:
        logger.info("[Search] DuckDuckGo results insufficient. Trying Google Search fallback...")
        try:
            from googlesearch import search as google_search
            for q in queries:
                try:
                    logger.info(f"[Google Search] Querying: {q}")
                    results = list(google_search(q, num_results=3))
                    for url in results:
                        if url and url not in urls:
                            urls.append(url)
                except Exception as google_single_err:
                    logger.warning(f"[Google Search] Query failed for '{q}': {google_single_err}")
        except Exception as google_err:
            logger.error(f"[Google Search] Failed to initialize Google Search: {google_err}")
            
    # Filter out common search engine URLs or noise
    filtered_urls = []
    ignored_domains = ['duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com', 'wikipedia.org', 'youtube.com']
    for url in urls:
        try:
            domain = urlparse(url).netloc.lower()
            if not any(ignored in domain for ignored in ignored_domains):
                filtered_urls.append(url)
        except Exception:
            pass
            
    # Return at most 5 URLs to keep it fast and low memory
    return filtered_urls[:5]

def deep_research_gather(idea, task_id=None, active_tasks_dict=None, queries=None):
    import time
    import random
    import gc
    import psutil
    from urllib.parse import urlparse
    import urllib.parse
    
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["current_step"] = "Searching the web for failure signals..."
        active_tasks_dict[task_id]["message"] = "Querying search engines..."
        
    urls = search_for_urls(idea, queries)
    
    if not urls:
        logger.info("[Scraper] No search results found. Using curated fallback database...")
        fallback_insight = get_offline_fallback(idea)
        warning_msg = f"[Warning] All search engines blocked. Using local fallback.\n\n{fallback_insight}"
        return {
            "urls": [],
            "combined_text": warning_msg,
            "raw_combined_markdown": warning_msg,
            "source_count": 0
        }
        
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["total_articles"] = len(urls)
        active_tasks_dict[task_id]["current_step"] = f"Found {len(urls)} target URLs."
        active_tasks_dict[task_id]["message"] = f"Beginning batch scrape of {len(urls)} targets..."
        
    logger.info(f"[Scraper] Deduplicated target URLs ({len(urls)}): {urls}")
    
    scraped_data = {}
    crawl4ai_success = False
    
    # Try Crawl4AI primary
    try:
        import asyncio
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher, RateLimiter
        
        async def run_crawl4ai_scrape(url_list):
            browser_config = BrowserConfig(
                browser_type="chromium",
                headless=True,
                verbose=False,
                text_mode=True,      # Blocks images
                light_mode=True,     # Disables background features
                extra_args=[
                    "--blink-settings=imagesEnabled=false",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--single-process",   # REDUCES MEMORY FOOTPRINT
                    "--no-zygote",        # DISABLES ZYGOTE PROCESS
                    "--disable-gpu",      # NO GPU IN HEADLESS
                    "--js-flags=--max-old-space-size=512"  # LIMIT JS HEAP
                ]
            )
            prune_filter = PruningContentFilter(
                threshold=0.45,
                threshold_type="fixed",
                min_word_threshold=15
            )
            md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)
            
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                markdown_generator=md_generator,
                remove_overlay_elements=True,
                exclude_external_links=True,
                page_timeout=35000,
                wait_for="css:body",
                delay_before_return_html=1.5
            )
            
            nonlocal scraped_data
            async with AsyncWebCrawler(config=browser_config) as crawler:
                for idx, url in enumerate(url_list):
                    netloc = urlparse(url).netloc
                    if active_tasks_dict and task_id:
                        active_tasks_dict[task_id]["current_step"] = f"Scraping {idx+1}/{len(url_list)}: {netloc}"
                        active_tasks_dict[task_id]["message"] = "Crawling page..."
                        
                    logger.info(f"[Crawl4AI] Scraping {idx+1}/{len(url_list)}: {url}")
                    try:
                        res = await crawler.arun(url=url, config=run_config)
                        if res.success:
                            content = getattr(res, 'fit_markdown', None) or res.markdown
                            if content and len(content.strip()) > 100:
                                scraped_data[url] = content
                                if active_tasks_dict and task_id:
                                    active_tasks_dict[task_id]["extracted_count"] += 1
                                logger.info(f"  [Success] Extracted {len(content)} chars")
                            else:
                                logger.warning(f"  [Warning] Empty content from {url}")
                        else:
                            logger.error(f"  [Error] Failed to crawl {url}: {res.error_message}")
                    except Exception as single_err:
                        logger.error(f"  [Error] Error crawling {url}: {single_err}")
                        
                    await asyncio.sleep(random.uniform(1.0, 3.0))
        
        try:
            asyncio.run(run_crawl4ai_scrape(urls))
        finally:
            # Force garbage collection and clean up chromium processes to solve memory leaks
            gc.collect()
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] in ('chromium', 'chrome', 'chromedriver'):
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        pass
        crawl4ai_success = len(scraped_data) > 0
        
    except Exception as e:
        logger.warning(f"[Warning] Crawl4AI failed: {e}. Falling back to requests+BeautifulSoup...")
        
    # Fallback Scraper: Requests + BeautifulSoup + Deduplication
    if not crawl4ai_success:
        logger.info("[Scraper] Running lightweight requests + BeautifulSoup scraper...")
        import requests
        import difflib
        from bs4 import BeautifulSoup
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        
        for idx, url in enumerate(urls):
            netloc = urlparse(url).netloc
            if active_tasks_dict and task_id:
                active_tasks_dict[task_id]["current_step"] = f"Scraping {idx+1}/{len(urls)}: {netloc} (Fallback)"
                active_tasks_dict[task_id]["message"] = "Fetching raw HTML..."
                
            logger.info(f"[Fallback] Scraping {idx+1}/{len(urls)}: {url}")
            try:
                headers = {'User-Agent': random.choice(user_agents)}
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for element in soup(["script", "style", "nav", "header", "footer"]):
                        element.decompose()
                    lines = (line.strip() for line in soup.get_text().splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    if len(text) > 100:
                        is_duplicate = False
                        for existing_text in scraped_data.values():
                            ratio = difflib.SequenceMatcher(None, text[:1000], existing_text[:1000]).ratio()
                            if ratio > 0.8:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            scraped_data[url] = text[:5000]
                            if active_tasks_dict and task_id:
                                active_tasks_dict[task_id]["extracted_count"] += 1
                            logger.info(f"  [Success] Extracted {len(text)} chars (BS4)")
                        else:
                            logger.warning(f"  [Warning] Duplicate content skipped: {url}")
                else:
                    print(f"  [Error] HTTP {r.status_code} on {url}")
            except Exception as single_err:
                print(f"  [Error] Failed to fetch {url}: {single_err}")
                
            time.sleep(random.uniform(0.5, 1.5))
            
    # Compile results
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
            print(f"[Scraper] Truncating combined text from {len(words)} to 8000 words...")
            combined_text = " ".join(words[:8000])
            
        with open("raw_data.txt", "w", encoding="utf-8") as f:
            f.write(combined_text)
            
        return {
            "urls": list(scraped_data.keys()),
            "combined_text": combined_text,
            "raw_combined_markdown": combined_text,
            "source_count": len(scraped_data)
        }
    else:
        print("[Scraper] No web data scraped successfully. Activating curated offline fallback database...")
        fallback_insight = get_offline_fallback(idea)
        warning_msg = f"[Warning] All search engines blocked. Using local fallback.\n\n{fallback_insight}"
        with open("raw_data.txt", "w", encoding="utf-8") as f:
            f.write(warning_msg)
        return {
            "urls": [],
            "combined_text": warning_msg,
            "raw_combined_markdown": warning_msg,
            "source_count": 0
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
    if not raw_text:
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
    
    if strategy_metadata is None:
        strategy_metadata = {
            "queries_used": queries or [
                f'{idea} failure post mortem',
                f'{idea} horror story',
                f'{idea} shut down',
                f'{idea} abandoned'
            ],
            "scraper_type": "crawl4ai_BS4_fallback",
            "prompt_version": 1
        }
        
    quality_score = calculate_quality_score(source_count, raw_text)
    logger.info(f"[Coroner] Quality score calculated: {quality_score}")
    
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["current_step"] = "Analyzing signals using local LLM..."
        active_tasks_dict[task_id]["message"] = "Extracting UX, Tech, and Cost failure patterns..."
        
    if "All search engines blocked" in raw_text:
        gathered_str = "Fallback used"
        cleaned_str = "Deduplicated fallback insight"
        cleaned_text = raw_text
    else:
        gathered_str = f"{source_count} sources scraped" if source_count > 0 else "0 sources scraped"
        cleaned_str = f"{source_count} unique signals"
        
        graveyard_lines = []
        for i, url in enumerate(urls_scraped):
            graveyard_lines.append(f"Source: Scraped Link {i+1} ({url})")
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
