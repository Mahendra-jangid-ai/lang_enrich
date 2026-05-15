import os
import re
import time
import copy
import asyncio
import platform
from datetime import datetime
from urllib.parse import urlparse
from typing import TypedDict, Dict, Any, List

import orjson
import tldextract
import trafilatura
import requests
from rapidfuzz import fuzz
from dotenv import load_dotenv
from tavily import TavilyClient
from serpapi import GoogleSearch
from crawl4ai import AsyncWebCrawler
from newspaper import Article
from langgraph.graph import StateGraph, END
from langchain_ollama import OllamaLLM
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from firecrawl import FirecrawlApp
except Exception:
    FirecrawlApp = None

try:
    import spacy
except Exception:
    spacy = None

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

# =========================================================
# OPTIONAL NLP
# =========================================================

if spacy is not None:
    try:
        nlp = spacy.load("en_core_web_lg")
    except Exception:
        nlp = None
else:
    nlp = None

# =========================================================
# API COUNTERS
# =========================================================

TAVILY_CALLS = 0
SERPAPI_CALLS = 0
APIFY_CALLS = 0
OLLAMA_CALLS = 0
FIRECRAWL_CALLS = 0

# =========================================================
# LOGGER
# =========================================================

def log(message: str) -> None:
    current = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{current}] {message}")

# =========================================================
# TIMER
# =========================================================

class Timer:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.start = time.time()
        log(f"STARTED: {self.name}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        total = round(time.time() - self.start, 2)
        log(f"FINISHED: {self.name} ({total}s)")

# =========================================================
# LLM
# =========================================================

llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0)

# =========================================================
# SCHEMAS
# =========================================================

def get_empty_company_schema() -> Dict[str, Any]:
    return {
        "company": {
            "legal_name": "",
            "brand_name": "",
            "website": "",
            "domain": "",
            "company_number": "",
            "GST_number": "",
            "status": "",
            "company_type": "",
            "incorporation_date": "",
            "founded": "",
            "previous_names": [],
            "industry": "",
            "sic_codes": [],
            "description": "",
            "headquarters": {
                "address": "",
                "city": "",
                "state": "",
                "postal_code": "",
                "country": ""
            },
            "locations": [
            {
                "address": "",
                "city": "",
                "state": "",
                "postal_code": "",
                "country": "",
                "type": ""
            }
            ],
            "contact": {
                "phone": "",
                "email": "",
                "support_email": "",
                "website": ""
            },
            "company_size": "",
            "employee_count_estimate": "",
            "operating_status": "",
            "linkedin": ""
        },
        "services": [],
        "products": [],
        "business_model": {
            "revenue_streams": [],
            "pricing_model": "",
            "customer_segments": []
        },
        "decision_makers": [
            {"name": "", "title": "", "linkedin_profile": "", "source": "","email":"","phone": "","experience": "","education": "","professional_summary": "","professional_summary": "","professional_summary": ""}
        ],
        "corporate_structure": {
            "holding_company": "",
            "subsidiaries": [],
            "related_companies": [],
            "investors": []
        },
        "financial_snapshot": {
            "revenue": "",
            "profit": "",
            "valuation": "",
            "funding_rounds": [],
            "accounts_type": "",
            "last_accounts_date": "",
            "next_accounts_due": ""
        },
        "market_intelligence": {
            "competitors": [
                {"name": "", "description": "", "website": "", "source": ""}
            ],
            "market_position": ""
        },
        "news": [],
        "online_presence": {
            "linkedin_followers_estimate": "",
            "monthly_web_visits_estimate": "",
            "trustpilot_rating": "",
            "trustpilot_reviews": "",
            "app_downloads_estimate": ""
        },
        "lead_generation_targets": {
            "primary_decision_maker": "",
            "secondary_targets": [],
            "general_contact_email": "",
            "general_phone": "",
            "sales_signals": []
        },
        "ai_insights": {
            "summary": "",
            "growth_stage": "",
            "funding_stage": "",
            "business_health_score": 0,
            "confidence_score": 0
        },
        "sources": [],
        "meta": {
            "last_updated": "",
            "data_completeness": 0,
            "duplicate_flags": [],
            "notes": []
        }
    }


def get_empty_person_schema() -> Dict[str, Any]:
    return {
        "full_name": "",
        "email": "",
        "current_company": "",
        "current_role": "",
        "location": "",
        "linkedin_url": "",
        "linkedin_headline": "",
        "linkedin_about": "",
        "professional_summary": "",
        "experience": [],
        "education": [],
        "contact_info": {"email": "", "phone": ""}
    }


FINAL_SCHEMA = get_empty_company_schema()
PERSON_SCHEMA = get_empty_person_schema()

# =========================================================
# STATE
# =========================================================

class AgentState(TypedDict):
    query: str
    search_results: List[Dict[str, Any]]
    linkedin_data: Dict[str, Any]
    website_content: str
    firecrawl_content: str
    company_data: Dict[str, Any]
    decision_makers_data: List[Dict[str, Any]]
    final_output: Dict[str, Any]

# =========================================================
# HELPERS
# =========================================================

def dumps(data: Any) -> str:
    return orjson.dumps(data).decode()


def safe_json(text: Any) -> Dict[str, Any]:
    if isinstance(text, dict):
        return text
    if text is None:
        return {}
    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        if not isinstance(text, str):
            text = str(text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return orjson.loads(match.group())
    except Exception as e:
        log(f"JSON ERROR: {e}")
    return {}


def normalize_company_name(name: str) -> str:
    return re.sub(
        r"\b(inc|llc|ltd|private|limited|corp|corporation)\b",
        "",
        (name or "").lower(),
    ).strip()


def dedupe_companies(companies: List[Any]) -> List[Any]:
    deduped = []
    seen = []
    for comp in companies or []:
        if isinstance(comp, str):
            cname = comp
        elif isinstance(comp, dict):
            cname = comp.get("name", "")
        else:
            continue
        normalized = normalize_company_name(cname)
        duplicate = False
        for existing in seen:
            if fuzz.ratio(normalized, existing) > 90:
                duplicate = True
                break
        if not duplicate:
            seen.append(normalized)
            deduped.append(comp)
    return deduped


def extract_domain(url: str) -> str:
    try:
        ext = tldextract.extract(url or "")
        if not ext.domain:
            return ""
        return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    except Exception:
        return ""


def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    return list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)))


def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    phones = re.findall(r"(\+?\d[\d\s\-\(\)]{7,}\d)", text)
    cleaned = []
    for p in phones:
        p = re.sub(r"\s+", " ", p).strip()
        if len(re.sub(r"\D", "", p)) >= 8:
            cleaned.append(p)
    return list(dict.fromkeys(cleaned))


def deep_copy_schema() -> Dict[str, Any]:
    return copy.deepcopy(FINAL_SCHEMA)

# =========================================================
# CRITICAL FIELDS / MISSING FIELD DETECTION
# =========================================================

CRITICAL_FIELDS = [
    "company.employee_count_estimate",
    "company.linkedin",
    "decision_makers",
    "corporate_structure.subsidiaries",
    "market_intelligence.competitors",
    "company.contact.email",
    "company.contact.phone",
    "company.website",
    "company.domain",
    "company.brand_name",
    "decision_makers.name",
    "decision_makers.title",
    "decision_makers.linkedin_profile",
    "decision_makers.email",
    "decision_makers.phone",
    "decision_makers.experience",
    "news",
    "company.description",
    "company.industry",
    
]


def get_nested(data: Dict[str, Any], path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def detect_missing_fields(data: Dict[str, Any]) -> List[str]:
    missing = []
    for field in CRITICAL_FIELDS:
        value = get_nested(data, field)
        if value in (None, "", [], {}):
            missing.append(field)
    return missing


def generate_hypothesis_queries(company_name: str, missing_fields: List[str]) -> List[str]:
    queries = []
    for field in missing_fields:
        if "employee_count" in field:
            queries.extend([
                f"{company_name} linkedin employees",
                f"{company_name} company size",
                f"{company_name} employee count",
            ])
        elif "decision_makers" in field:
            queries.extend([
                f"site:linkedin.com/in {company_name} CEO",
                f"site:linkedin.com/in {company_name} Founder",
                f"site:linkedin.com/in {company_name} CTO",
                f"{company_name} leadership team",
            ])
        elif "subsidiaries" in field:
            queries.extend([
                f"{company_name} subsidiaries",
                f"{company_name} holdings",
                f"{company_name} parent company",
            ])
        elif "competitors" in field:
            queries.extend([
                f"{company_name} competitors",
                f"{company_name} alternatives",
                f"companies like {company_name}",
            ])
        elif "linkedin" in field:
            queries.extend([
                f"site:linkedin.com/company {company_name}",
                f"{company_name} linkedin",
            ])
        elif "phone" in field:
            queries.extend([
                f"{company_name} contact phone",
                f"{company_name} support number",
            ])
        elif "email" in field:
            queries.extend([
                f"{company_name} contact email",
                f"{company_name} support email",
            ])
    return list(dict.fromkeys(queries))

# =========================================================
# SEARCH / SOURCE HELPERS
# =========================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def tavily_search(query: str) -> Dict[str, Any]:
    global TAVILY_CALLS
    TAVILY_CALLS += 1
    log(f"TAVILY CALL #{TAVILY_CALLS}")
    client = TavilyClient(api_key=TAVILY_API_KEY)
    with Timer("Tavily Search"):
        return client.search(
            query=query,
            search_depth="advanced",
            max_results=10,
            include_answer=True,
            include_raw_content=True,
        )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def serpapi_search(query: str) -> Dict[str, Any]:
    global SERPAPI_CALLS
    SERPAPI_CALLS += 1
    log(f"SERPAPI CALL #{SERPAPI_CALLS}")
    with Timer("SerpAPI"):
        params = {"engine": "google", "q": query, "num": 10, "api_key": SERPAPI_API_KEY}
        return GoogleSearch(params).get_dict()


def merge_results(tavily_data: Dict[str, Any], serpapi_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    merged = []
    for item in (tavily_data or {}).get("results", []):
        if isinstance(item, dict):
            merged.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "source": "tavily",
            })
    for item in (serpapi_data or {}).get("organic_results", []):
        if isinstance(item, dict):
            merged.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "content": item.get("snippet", ""),
                "source": "serpapi",
            })
    return merged


def firecrawl_scrape(url: str) -> str:
    global FIRECRAWL_CALLS
    if not FIRECRAWL_API_KEY or FirecrawlApp is None:
        return ""
    FIRECRAWL_CALLS += 1
    log(f"FIRECRAWL CALL #{FIRECRAWL_CALLS}")
    try:
        app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        result = app.scrape_url(url=url, formats=["markdown"])
        return result.get("markdown", "") if isinstance(result, dict) else ""
    except Exception as e:
        log(f"FIRECRAWL ERROR: {e}")
        return ""


async def crawl_site(url: str) -> str:
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            return result.markdown or ""
    except Exception as e:
        log(f"CRAWL ERROR: {e}")
        return ""


def extract_clean_text(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        return trafilatura.extract(downloaded) or ""
    except Exception:
        return ""


def linkedin_company_finder(company: str) -> str:
    query = f"site:linkedin.com/company {company}"
    data = serpapi_search(query)
    for item in data.get("organic_results", []):
        url = item.get("link", "") if isinstance(item, dict) else ""
        if "linkedin.com/company/" in url:
            return url
    return ""


def linkedin_scraper(query: str) -> Any:
    global APIFY_CALLS
    if not APIFY_API_KEY:
        return []
    APIFY_CALLS += 1
    log(f"APIFY CALL #{APIFY_CALLS}")
    url = (
        "https://api.apify.com/v2/acts/"
        "apimaestro~linkedin-profile-scraper/"
        "run-sync-get-dataset-items"
    )
    payload = {"queries": [query], "maxPagesPerQuery": 1}
    headers = {"Authorization": f"Bearer {APIFY_API_KEY}"}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        return response.json()
    except Exception as e:
        log(f"APIFY ERROR: {e}")
        return []


def ollama_json(prompt: str) -> Dict[str, Any]:
    global OLLAMA_CALLS
    OLLAMA_CALLS += 1
    log(f"OLLAMA CALL #{OLLAMA_CALLS}")
    try:
        response = llm.invoke(prompt)
        return safe_json(response)
    except Exception as e:
        log(f"OLLAMA ERROR: {e}")
        return {}

# =========================================================
# NODES
# =========================================================

def search_node(state: AgentState) -> AgentState:
    query = state["query"]
    tav = tavily_search(query)
    serp = serpapi_search(query)
    merged = merge_results(tav, serp)
    return {**state, "search_results": merged}


def website_node(state: AgentState) -> AgentState:
    website = ""
    for item in state["search_results"]:
        url = item.get("url", "") if isinstance(item, dict) else ""
        if url.startswith("http") and "linkedin" not in url:
            website = url
            break
    if not website:
        return {**state, "website_content": "", "firecrawl_content": ""}

    crawl4ai_content = asyncio.run(crawl_site(website))
    firecrawl_content = firecrawl_scrape(website)
    trafilatura_content = extract_clean_text(website)
    merged_content = "\n\n".join([crawl4ai_content, firecrawl_content, trafilatura_content])
    return {**state, "website_content": merged_content, "firecrawl_content": firecrawl_content}


def linkedin_node(state: AgentState) -> AgentState:
    company = state["query"]
    linkedin_url = linkedin_company_finder(company)
    linkedin_data = linkedin_scraper(company)
    return {**state, "linkedin_data": {"linkedin_url": linkedin_url, "profiles": linkedin_data}}


def decision_maker_agent(state: AgentState) -> AgentState:
    company = state["query"]
    searches = [
        f"site:linkedin.com/in {company} CEO",
        f"site:linkedin.com/in {company} Founder",
        f"site:linkedin.com/in {company} CTO",
        f"site:linkedin.com/in {company} COO",
        f"{company} leadership team",
    ]

    results = []
    for q in searches:
        data = serpapi_search(q)
        for item in data.get("organic_results", []):
            if isinstance(item, dict):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

    prompt = f"""
Extract REAL decision makers.

Need:
- name
- title
- linkedin_profile
- source

Rules:
- no hallucinations
- valid json only
- linkedin url required
- max 5 decision makers
- only real profiles
- prefer profiles that clearly tie to {company} in their title/snippet
- prefer company experience/current employer over generic bio text
- if the title is not clear, use the snippet or other context to determine the most likely title
- if a profile does not clearly tie to {company}, exclude it
- if data is unclear or contradictory, provide the most likely answer and explain in notes

Results:
{dumps(results)}

Return:
{{
  "decision_makers": []
}}
"""
    extracted = ollama_json(prompt)
    return {**state, "decision_makers_data": extracted.get("decision_makers", [])}


def enrichment_agent(state: AgentState) -> AgentState:
    prompt = f"""
You are a world-class company enrichment AI.

Extract maximum structured data.

VERY IMPORTANT RULES:
- NEVER HALLUCINATE
- RETURN VALID JSON ONLY
- USE PROVIDED SCHEMA EXACTLY
- IF UNKNOWN KEEP EMPTY
- COMPETITORS MUST INCLUDE WEBSITE
- SUBSIDIARIES MUST BE REAL
- EMPLOYEE COUNT SHOULD PRIORITIZE LINKEDIN
- DECISION MAKERS MUST INCLUDE LINKEDIN
- NO MARKDOWN

SEARCH RESULTS:
{dumps(state["search_results"])}

WEBSITE:
{state["website_content"]}

LINKEDIN:
{dumps(state["linkedin_data"])}

DECISION MAKERS:
{dumps(state.get("decision_makers_data", []))}

OUTPUT SCHEMA:
{dumps(FINAL_SCHEMA)}

RETURN ONLY JSON.
"""
    data = ollama_json(prompt)
    return {**state, "company_data": data}


def retry_enrichment_node(state: AgentState) -> AgentState:
    current = state["company_data"]
    missing = detect_missing_fields(current)
    log(f"MISSING FIELDS: {missing}")
    if not missing:
        return state

    queries = generate_hypothesis_queries(state["query"], missing)
    additional_results = []
    for q in queries:
        tav = tavily_search(q)
        serp = serpapi_search(q)
        additional_results.extend(merge_results(tav, serp))

    combined = state["search_results"] + additional_results
    prompt = f"""
Re-enrich ONLY missing fields.

Missing:
{dumps(missing)}

Current Data:
{dumps(current)}

Additional Search Data:
{dumps(combined)}

Output Schema:
{dumps(FINAL_SCHEMA)}

Return FULL JSON ONLY.
"""
    new_data = ollama_json(prompt)
    return {**state, "search_results": combined, "company_data": new_data}


def news_agent(state: AgentState) -> AgentState:
    news = []
    for item in state["search_results"][:10]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            continue
        try:
            article = Article(url)
            article.download()
            article.parse()
            article.nlp()
            news.append({
                "title": article.title,
                "summary": article.summary,
                "date": str(article.publish_date),
                "url": url,
            })
        except Exception:
            pass
    return {**state, "news": news}

# =========================================================
# OUTPUT HELPERS
# =========================================================

def normalize_decision_makers(dms: Any, company_name: str) -> List[Dict[str, Any]]:
    cleaned = []
    seen = set()
    for item in dms or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        title = (item.get("title") or "").strip()
        linkedin_profile = (item.get("linkedin_profile") or item.get("linkedin_url") or "").strip()
        source = (item.get("source") or "").strip()

        if linkedin_profile and not linkedin_profile.startswith("http"):
            linkedin_profile = "https://www.linkedin.com/in/" + linkedin_profile.strip("/")

        key = (name.lower(), title.lower(), linkedin_profile.lower())
        if key in seen:
            continue
        seen.add(key)

        # If the person data is actually a bio/profile summary, keep it only when it clearly ties to the company.
        if title and company_name.lower() not in title.lower() and company_name.lower() not in (name + " " + source).lower():
            # still keep the item if the LinkedIn URL exists and title is not clearly wrong
            if not linkedin_profile:
                continue

        if linkedin_profile:
            cleaned.append({
                "name": name,
                "title": title,
                "linkedin_profile": linkedin_profile,
                "source": source,
            })
    return cleaned[:5]


def normalize_competitors(competitors: Any) -> List[Dict[str, Any]]:
    cleaned = []
    seen = set()
    for item in competitors or []:
        if isinstance(item, str):
            item = {"name": item, "description": "", "website": "", "source": "llm"}
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        website = (item.get("website") or "").strip()
        description = (item.get("description") or "").strip()
        source = (item.get("source") or "").strip()
        if website and not website.startswith("http"):
            website = "https://" + website.lstrip("/")
        key = (name.lower(), website.lower())
        if key in seen:
            continue
        seen.add(key)
        if name:
            cleaned.append({
                "name": name,
                "description": description,
                "website": website,
                "source": source,
            })
    return cleaned[:5]


def final_merge(state: AgentState) -> AgentState:
    final = deep_copy_schema()
    enriched = state.get("company_data", {})
    if isinstance(enriched, dict):
        for key, value in enriched.items():
            final[key] = value

    final["company"]["linkedin"] = final["company"].get("linkedin") or state.get("linkedin_data", {}).get("linkedin_url", "")
    final["company"]["employee_count_estimate"] = final["company"].get("employee_count_estimate") or state.get("linkedin_data", {}).get("employee_count_estimate", "")

    final["decision_makers"] = normalize_decision_makers(
        state.get("decision_makers_data", []),
        state.get("query", ""),
    )

    competitors = ((final.get("market_intelligence", {}) or {}).get("competitors", []))
    if not isinstance(competitors, list):
        competitors = []
    final["market_intelligence"]["competitors"] = normalize_competitors(competitors)

    # Fill contact defaults from website content
    website_content = state.get("website_content", "")
    if not final["company"]["contact"]["email"]:
        emails = extract_emails(website_content)
        if emails:
            final["company"]["contact"]["email"] = emails[0]
    if not final["company"]["contact"]["phone"]:
        phones = extract_phones(website_content)
        if phones:
            final["company"]["contact"]["phone"] = phones[0]

    if not final["company"].get("website"):
        for item in state.get("search_results", []):
            if isinstance(item, dict) and item.get("url", "").startswith("http"):
                final["company"]["website"] = item["url"]
                final["company"]["contact"]["website"] = item["url"]
                break

    if not final["company"].get("domain") and final["company"].get("website"):
        final["company"]["domain"] = extract_domain(final["company"]["website"])

    if not final["company"].get("brand_name"):
        final["company"]["brand_name"] = state.get("query", "")
    if not final["company"].get("legal_name"):
        final["company"]["legal_name"] = final["company"]["brand_name"]

    final["news"] = state.get("news", [])
    final["sources"] = ["tavily", "serpapi", "crawl4ai", "firecrawl", "trafilatura", "apify", "ollama"]
    final["meta"]["last_updated"] = str(datetime.now())
    missing = detect_missing_fields(final)
    final["meta"]["data_completeness"] = int(((len(CRITICAL_FIELDS) - len(missing)) / len(CRITICAL_FIELDS)) * 100)
    final["meta"]["duplicate_flags"] = []
    final["meta"]["notes"] = [f"Missing fields: {missing}"]

    return {**state, "final_output": final}

# =========================================================
# SAVE OUTPUT
# =========================================================

def save_final_output(final_data: Dict[str, Any]) -> str:
    filename = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "wb") as f:
        f.write(orjson.dumps(final_data, option=orjson.OPT_INDENT_2))
    log(f"OUTPUT SAVED -> {filename}")
    return filename

# =========================================================
# GRAPH
# =========================================================

graph = StateGraph(AgentState)

graph.add_node("search_node", search_node)
graph.add_node("website_node", website_node)
graph.add_node("linkedin_node", linkedin_node)
graph.add_node("decision_maker_agent", decision_maker_agent)
graph.add_node("enrichment_agent", enrichment_agent)
graph.add_node("retry_enrichment_node", retry_enrichment_node)
graph.add_node("news_agent", news_agent)
graph.add_node("final_merge", final_merge)

graph.set_entry_point("search_node")
graph.add_edge("search_node", "website_node")
graph.add_edge("website_node", "linkedin_node")
graph.add_edge("linkedin_node", "decision_maker_agent")
graph.add_edge("decision_maker_agent", "enrichment_agent")
graph.add_edge("enrichment_agent", "retry_enrichment_node")
graph.add_edge("retry_enrichment_node", "news_agent")
graph.add_edge("news_agent", "final_merge")
graph.add_edge("final_merge", END)

app = graph.compile()

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    log("SYSTEM STARTED")
    query = input("\nEnter company name: ").strip()
    start = time.time()

    result = app.invoke({
        "query": query,
        "search_results": [],
        "linkedin_data": {},
        "website_content": "",
        "firecrawl_content": "",
        "company_data": {},
        "decision_makers_data": [],
        "final_output": {},
    })

    total_time = round(time.time() - start, 2)

    print("\n")
    print("=" * 80)
    print("API STATS")
    print("=" * 80)
    print(f"TAVILY CALLS: {TAVILY_CALLS}")
    print(f"SERPAPI CALLS: {SERPAPI_CALLS}")
    print(f"APIFY CALLS: {APIFY_CALLS}")
    print(f"FIRECRAWL CALLS: {FIRECRAWL_CALLS}")
    print(f"OLLAMA CALLS: {OLLAMA_CALLS}")
    print(f"\nTOTAL TIME: {total_time}s")

    print("\n")
    print("=" * 80)
    print("FINAL OUTPUT")
    print("=" * 80)
    print(orjson.dumps(result["final_output"], option=orjson.OPT_INDENT_2).decode())

    save_final_output(result["final_output"])
