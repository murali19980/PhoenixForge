import sys
import json
import os
import requests
import time
import urllib.parse
import difflib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from duckduckgo_search import DDGS
import psutil
from llm_router import ask_llm_json, CONFIG

MEMORY_FILE = "memory.jsonl"

FALLBACK_DATABASE = {
    "resume": "Autopsy: AI resume tools fail because recruiters detect robotic language. 70% of resumes containing 'spearheaded' or 'synergized' are auto-rejected by ATS. Churn rate reaches 95% after one use.",
    "scheduler": "Autopsy: Social media scheduling apps fail due to API token rate-limiting on X and LinkedIn. Pricing model doesn't cover token costs, resulting in $600/month losses at 1000 users.",
    "fitness": "Autopsy: Fitness and workout logging apps suffer 90% churn by day 7 because users hate manual data entry. Failing to integrate with smart wearables causes complete failure.",
    "chatbot": "Autopsy: Customer support chatbots fail because they hallucinate facts and cost $0.05 per conversation. Retailers abandon them because users get frustrated with looping answers.",
    "ecommerce": "Autopsy: Dropshipping and niche e-commerce sites fail due to razor-thin 5% margins and ad acquisition costs exceeding average order value. 80% cart abandonment is normal.",
    "delivery": "Autopsy: Local courier and food delivery startups fail because of the low density of orders and massive driver acquisition costs. Unit economics are negative on every single trip.",
    "marketplace": "Autopsy: Two-sided marketplaces fail because they cannot solve the chicken-and-egg problem. Without supply (sellers), buyers leave; without buyers, sellers churn.",
    "education": "Autopsy: EdTech platforms fail because students lack completion discipline (MOOC completion rates are <6%). Selling to universities has an impossible 18-month sales cycle.",
    "crypto": "Autopsy: Web3 and crypto projects fail due to gas fee spikes, security exploits, and lack of real utility. 99% of users are speculative and churn as soon as token prices drop.",
    "finance": "Autopsy: Personal finance apps fail because they require connecting bank APIs which frequently disconnect. Users are uncomfortable sharing financial credentials.",
    "healthcare": "Autopsy: Digital health platforms fail due to complex HIPAA compliance requirements and resistance from doctors to adopt new software. Sales cycles are slow.",
    "travel": "Autopsy: Travel itinerary planning apps fail because people only travel 1-2 times a year. Retention is near-zero, making customer acquisition costs unsustainable.",
    "gaming": "Autopsy: Indie multiplayer games fail because they lack the critical mass of active players. New players join empty lobbies and quit within 3 minutes.",
    "email": "Autopsy: Email productivity tools fail because Google and Microsoft integrate similar features for free. Users are reluctant to pay for standalone email extensions.",
    "security": "Autopsy: Cybersecurity startups fail because selling to enterprise CISOs requires extensive compliance certifications (SOC2 Type II, ISO27001) that cost $50k+ upfront.",
    "recruitment": "Autopsy: Job boards fail because they compete with LinkedIn. Companies refuse to pay for postings that don't yield qualified candidates.",
    "collaboration": "Autopsy: Team wiki and documentation tools fail because Slack and Notion own the market. Users resist moving docs from where they already work.",
    "analytics": "Autopsy: SaaS analytics tools fail because developers build simple dashboards in-house instead of paying a recurring fee. Data pipelines break, leading to churn.",
    "crm": "Autopsy: Sales CRMs fail because sales reps hate manual data entry. Unless data is auto-logged, the CRM remains empty and gets cancelled.",
    "marketing": "Autopsy: SEO optimization software fails because search engine algorithms update constantly, wiping out rankings overnight. Users cancel when their traffic drops.",
    "productivity": "Autopsy: To-do lists and task managers fail because the market is saturated with free tools. The switching cost is zero, leading to 90% monthly churn.",
    "dating": "Autopsy: Niche dating apps fail because of the demographic imbalance (often 9:1 male-to-female ratio). Once a user finds a match, they delete the app.",
    "real estate": "Autopsy: Property management platforms fail because landlords are tech-averse. Collecting rent through the app incurs transaction fees they refuse to pay.",
    "iot": "Autopsy: Smart home IoT hardware fails because manufacturing margins are thin, and firmware updates break device compatibility, causing massive return rates.",
    "hardware": "Autopsy: Hardware startups fail because tooling and manufacturing costs require large upfront capital. Shipping delays of 6+ months kill consumer trust.",
    "ai": "Autopsy: AI wrapper tools fail because OpenAI or Google releases the same feature natively. High API costs combined with zero moat results in instant churn.",
    "music": "Autopsy: Music streaming and licensing platforms fail because record labels demand 70% of revenues in royalties, leaving zero margin for the platform.",
    "video": "Autopsy: Video hosting and editing platforms fail due to massive AWS bandwidth costs. Free users upload gigabytes of files, draining company cash.",
    "news": "Autopsy: Subscription news sites fail because users bypass paywalls. Banner ads generate less than $1 CPM, which doesn't cover content production costs.",
    "blog": "Autopsy: Content management systems fail because WordPress, Substack, and Medium dominate. Creators prefer platforms with built-in discovery.",
    "search": "Autopsy: Specialized search engines fail because Google's generalized search is good enough. Crawling the web requires millions in server costs.",
    "social network": "Autopsy: Social networks fail because of the network effect. Users join but leave when their friends aren't active, causing a death spiral.",
    "messaging": "Autopsy: Secure messaging apps fail because users refuse to switch away from WhatsApp or iMessage. Privacy is valued, but convenience wins.",
    "backup": "Autopsy: Cloud backup solutions fail because Apple, Microsoft, and Google bundle automatic backup in their operating systems.",
    "hosting": "Autopsy: Cloud hosting providers fail because they cannot compete with AWS, Azure, and GCP price cuts and data center footprints.",
    "dns": "Autopsy: DNS and CDN providers fail because enterprise clients require 100% SLA guarantees. A single minute of downtime results in massive legal penalties.",
    "weather": "Autopsy: Weather forecasting apps fail because every phone comes with a free, pre-installed weather app. Users won't pay for weather data.",
    "map": "Autopsy: Navigation and mapping tools fail because Google Maps and Apple Maps are free and integrated. Collecting mapping data is incredibly expensive.",
    "recipe": "Autopsy: Recipe and meal planning apps fail because recipes are free on blogs. Users hate paying a subscription to access basic cooking steps.",
    "events": "Autopsy: Event ticket booking sites fail because Eventbrite dominates. Charging ticket fees drives organizers to self-host or use competitors.",
    "ticket": "Autopsy: Customer ticketing systems fail because Zendesk owns the market. Switching ticketing software requires retraining support staff, which companies avoid.",
    "legal": "Autopsy: Legal tech platforms fail because lawyers charge by the hour and are disincentivized to use efficiency-increasing software.",
    "accounting": "Autopsy: Tax and accounting tools fail because tax laws change yearly. Building custom calculations is error-prone, leading to audit liabilities.",
    "tax": "Autopsy: Tax filing calculators fail because government portals are offering free filing. The trust barrier for financial calculations is high.",
    "portfolio": "Autopsy: Design portfolio builders fail because designers prefer hosting on Behance, Dribbble, or free GitHub Pages.",
    "api": "Autopsy: API monitoring tools fail because developers use open-source library tools like Prometheus and Grafana for free.",
    "dashboard": "Autopsy: Internal tool dashboard builders fail because companies use Retool or build basic pages in-house to keep data secure.",
    "extension": "Autopsy: Browser extensions fail because browser updates break extension APIs constantly, requiring ongoing maintenance for zero revenue.",
    "widgets": "Autopsy: Desktop widgets fail because users prefer clean screens. The novelty wears off in 3 days, causing 98% retention drop.",
    "default": "Autopsy: Startup failure analysis shows 3 major causes: 1. Building something nobody wants (34% of cases). 2. Running out of money due to high marketing/API costs (22% of cases). 3. Getting crushed by incumbent platforms changing their policies or APIs (18% of cases)."
}

def system_audit():
    ram = psutil.virtual_memory().total / (1024**3)
    try:
        import subprocess
        vram = int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.total','--format=csv,noheader,nounits'], encoding='utf-8').split('\n')[0]) / 1024
    except:
        vram = 0
    print(f"[System] RAM: {ram:.1f}GB, VRAM: {vram:.1f}GB")
    return {"ram": ram, "vram": vram}

def get_offline_fallback(idea):
    matched_insights = []
    idea_lower = idea.lower()
    for key, insight in FALLBACK_DATABASE.items():
        if key in idea_lower:
            matched_insights.append(f"[Curated Fallback - {key.capitalize()}] {insight}")
    
    if not matched_insights:
        matched_insights.append(f"[Curated Fallback - General] {FALLBACK_DATABASE['default']}")
        
    return "\n".join(matched_insights)

def search_for_urls(idea):
    import time
    import random
    
    queries = [
        f'{idea} failure post mortem',
        f'{idea} horror story',
        f'{idea} shut down',
        f'{idea} abandoned'
    ]
    
    urls = set()
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
    ]
    
    print("[Search] Querying DuckDuckGo...")
    for q in queries:
        try:
            headers = {'User-Agent': random.choice(user_agents)}
            with DDGS(headers=headers) as ddgs:
                results = list(ddgs.text(q, max_results=4))
                for r in results:
                    href = r.get('href')
                    if href and href not in urls:
                        if any(x in href for x in ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com']):
                            continue
                        urls.add(href)
            time.sleep(1.0)
        except Exception as e:
            print(f"[Warning] DDG query failed: {e}")
            
    # Fallback to google search (googlesearch-python)
    if len(urls) < 5:
        print("[Search] DDG yielded few results. Trying Google Search fallback...")
        for q in queries:
            try:
                from googlesearch import search
                google_results = search(q, num_results=4)
                for url in google_results:
                    if url and url not in urls:
                        if any(x in url for x in ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com']):
                            continue
                        urls.add(url)
            except Exception as e:
                print(f"[Warning] Google search query failed: {e}")
                
    return list(urls)[:15]

def deep_research_gather(idea, task_id=None, active_tasks_dict=None):
    import time
    import random
    from urllib.parse import urlparse
    import urllib.parse
    
    if active_tasks_dict and task_id:
        active_tasks_dict[task_id]["current_step"] = "Searching the web for failure signals..."
        active_tasks_dict[task_id]["message"] = "Querying search engines..."
        
    urls = search_for_urls(idea)
    
    if not urls:
        print("[Scraper] No search results found. Using curated fallback database...")
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
        
    print(f"[Scraper] Deduplicated target URLs ({len(urls)}): {urls}")
    
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
                extra_args=[
                    "--blink-settings=imagesEnabled=false",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
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
            
            dispatcher = MemoryAdaptiveDispatcher(
                rate_limiter=RateLimiter(
                    base_delay=(1.0, 3.0),
                    max_delay=15.0,
                    max_retries=2
                ),
                memory_threshold_percent=70.0,
                max_session_permit=1  # 1 concurrent tab only
            )
            
            nonlocal scraped_data
            async with AsyncWebCrawler(config=browser_config) as crawler:
                for idx, url in enumerate(url_list):
                    netloc = urlparse(url).netloc
                    if active_tasks_dict and task_id:
                        active_tasks_dict[task_id]["current_step"] = f"Scraping {idx+1}/{len(url_list)}: {netloc}"
                        active_tasks_dict[task_id]["message"] = "Crawling page..."
                        
                    print(f"[Crawl4AI] Scraping {idx+1}/{len(url_list)}: {url}")
                    try:
                        res = await crawler.arun(url=url, config=run_config)
                        if res.success:
                            content = getattr(res, 'fit_markdown', None) or res.markdown
                            if content and len(content.strip()) > 100:
                                scraped_data[url] = content
                                if active_tasks_dict and task_id:
                                    active_tasks_dict[task_id]["extracted_count"] += 1
                                print(f"  [Success] Extracted {len(content)} chars")
                            else:
                                print(f"  [Warning] Empty content from {url}")
                        else:
                            print(f"  [Error] Failed to crawl {url}: {res.error_message}")
                    except Exception as single_err:
                        print(f"  [Error] Error crawling {url}: {single_err}")
                        
                    await asyncio.sleep(random.uniform(1.0, 3.0))
        
        asyncio.run(run_crawl4ai_scrape(urls))
        crawl4ai_success = len(scraped_data) > 0
        
    except Exception as e:
        print(f"[Warning] Crawl4AI failed: {e}. Falling back to requests+BeautifulSoup...")
        
    # Fallback Scraper: Requests + BeautifulSoup + Deduplication
    if not crawl4ai_success:
        print("[Scraper] Running lightweight requests + BeautifulSoup scraper...")
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
                
            print(f"[Fallback] Scraping {idx+1}/{len(urls)}: {url}")
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
                            print(f"  [Success] Extracted {len(text)} chars (BS4)")
                        else:
                            print(f"  [Warning] Duplicate content skipped: {url}")
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

def step_by_step_extractor(raw_text, idea):
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
    print("[Coroner] Running Project Coroner analysis...")
    return ask_llm_json(base_prompt, raw_text)

def run_phoenixforge(idea, task_id=None, active_tasks_dict=None):
    print(f"[PhoenixForge] Scanning: {idea}")
    audit = system_audit()
    
    research_results = deep_research_gather(idea, task_id, active_tasks_dict)
    raw_text = research_results["combined_text"]
    urls_scraped = research_results["urls"]
    source_count = research_results["source_count"]
    
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
    
    data = step_by_step_extractor(raw_text, idea)
    
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
    print("[Report] Report saved to phoenixforge_report.md")
    
    # Save to SQLite history vault
    try:
        import history
        history.save_analysis(
            idea=idea,
            full_scraped_text=raw_text,
            heatmap_dict={'Cost': len(cost_risks), 'Tech': len(market_risks), 'UX': len(ux_risks)},
            fixes_list=failures,
            graveyard_text=cleaned_text,
            raw_content=report,
            raw_combined_markdown=raw_text,
            scraped_urls=urls_scraped,
            source_count=source_count
        )
        print("[History] Analysis successfully saved to SQLite history vault (phoenixforge.db)")
    except Exception as e:
        print(f"[History] Failed to save to SQLite database: {e}")
        
    return {
        "status": "success",
        "heatmap": {'Cost': len(cost_risks), 'Tech': len(market_risks), 'UX': len(ux_risks)},
        "fixes": failures,
        "graveyard": cleaned_text,
        "pipeline": pipeline_metadata,
        "raw_content": report
    }

if __name__ == "__main__":
    run_phoenixforge(sys.argv[1] if len(sys.argv) > 1 else "AI Resume Builder")
