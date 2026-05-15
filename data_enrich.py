# import os
# import re
# import json
# import time
# import asyncio
# import platform
# from urllib.parse import urlparse
# from datetime import datetime
# from typing import TypedDict, Dict, Any, List

# # =========================================================
# # WINDOWS FIX
# # =========================================================

# if platform.system() == "Windows":
#     asyncio.set_event_loop_policy(
#         asyncio.WindowsProactorEventLoopPolicy()
#     )

# # =========================================================
# # IMPORTS
# # =========================================================

# from dotenv import load_dotenv

# from tavily import TavilyClient

# from serpapi import GoogleSearch

# from crawl4ai import AsyncWebCrawler

# from playwright.async_api import async_playwright

# from newspaper import Article

# from langgraph.graph import StateGraph, END

# from langchain_ollama import OllamaLLM

# import requests

# # =========================================================
# # LOAD ENV
# # =========================================================

# load_dotenv()

# TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
# SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
# APIFY_API_KEY = os.getenv("APIFY_API_KEY")

# OLLAMA_MODEL = os.getenv(
#     "OLLAMA_MODEL",
#     "qwen2.5:14b"
# )

# # =========================================================
# # API COUNTERS
# # =========================================================

# TAVILY_CALLS = 0
# SERPAPI_CALLS = 0
# APIFY_CALLS = 0
# OLLAMA_CALLS = 0

# # =========================================================
# # LOGGER
# # =========================================================

# def log(message):

#     current = datetime.now().strftime(
#         "%H:%M:%S"
#     )

#     print(f"\n[{current}] {message}")

# # =========================================================
# # TIMER
# # =========================================================

# class Timer:

#     def __init__(self, name):

#         self.name = name

#     def __enter__(self):

#         self.start = time.time()

#         log(f"STARTED: {self.name}")

#     def __exit__(self, exc_type, exc_val, exc_tb):

#         total = round(
#             time.time() - self.start,
#             2
#         )

#         log(f"FINISHED: {self.name} ({total}s)")

# # =========================================================
# # LLM
# # =========================================================

# llm = OllamaLLM(
#     model=OLLAMA_MODEL,
#     temperature=0
# )

# # =========================================================
# # FINAL SCHEMA
# # =========================================================

# FINAL_SCHEMA = {

#     "person": {

#         "full_name": "",
#         "email": "",
#         "current_company": "",
#         "current_role": "",

#         "location": "",

#         "linkedin_url": "",
#         "linkedin_headline": "",
#         "linkedin_about": "",

#         "professional_summary": "",

#         "experience": [],

#         "education": [],

#         "contact_info": {
#             "email": "",
#             "phone": ""
#         }
#     },

#     "company": {

#         "legal_name": "",
#         "brand_name": "",
#         "website": "",
#         "domain": "",

#         "company_number": "",
#         "GST_number": "",

#         "status": "",
#         "company_type": "",

#         "incorporation_date": "",
#         "founded": "",

#         "previous_names": [],

#         "industry": "",

#         "sic_codes": [],

#         "description": "",

#         "headquarters": {
#             "address": "",
#             "city": "",
#             "state": "",
#             "postal_code": "",
#             "country": ""
#         },

#         "locations": [],

#         "contact": {
#             "phone": "",
#             "email": "",
#             "support_email": "",
#             "website": ""
#         },

#         "company_size": "",

#         "employee_count_estimate": "",

#         "operating_status": "",

#         "linkedin": ""
#     },

#     "services": [],

#     "products": [],

#     "business_model": {

#         "revenue_streams": [],

#         "pricing_model": "",

#         "customer_segments": []
#     },

#     "decision_makers": [

#         {
#             "name": "",
#             "title": "",
#             "linkedin_profile": "",
#             "source": ""
#         }
#     ],

#     "corporate_structure": {

#         "holding_company": "",

#         "subsidiaries": [],

#         "related_companies": [],

#         "investors": []
#     },

#     "financial_snapshot": {

#         "revenue": "",

#         "profit": "",

#         "valuation": "",

#         "funding_rounds": [],

#         "accounts_type": "",

#         "last_accounts_date": "",

#         "next_accounts_due": ""
#     },

#     "market_intelligence": {

#         "competitors": [

#             {
#                 "name": "",
#                 "description": "",
#                 "website": "",
#                 "source": ""
#             }
#         ],

#         "market_position": ""
#     },

#     "news": [],

#     "online_presence": {

#         "linkedin_followers_estimate": "",

#         "monthly_web_visits_estimate": "",

#         "trustpilot_rating": "",

#         "trustpilot_reviews": "",

#         "app_downloads_estimate": ""
#     },

#     "lead_generation_targets": {

#         "primary_decision_maker": "",

#         "secondary_targets": [],

#         "general_contact_email": "",

#         "general_phone": "",

#         "sales_signals": []
#     },

#     "ai_insights": {

#         "summary": "",

#         "growth_stage": "",

#         "funding_stage": "",

#         "business_health_score": 0,

#         "confidence_score": 0
#     },

#     "sources": [],

#     "meta": {

#         "last_updated": "",

#         "data_completeness": 0,

#         "duplicate_flags": [],

#         "notes": []
#     }
# }

# # =========================================================
# # STATE
# # =========================================================

# class AgentState(TypedDict):

#     query: str

#     query_type: str

#     search_results: List[Dict[str, Any]]

#     linkedin_data: Dict[str, Any]

#     website_content: str

#     company_data: Dict[str, Any]

#     person_data: Dict[str, Any]

#     competitors: List[Dict[str, Any]]

#     related_companies: List[Dict[str, Any]]

#     news: List[Dict[str, Any]]

#     final_output: Dict[str, Any]

# # =========================================================
# # HELPERS
# # =========================================================

# def is_email(value):

#     return bool(
#         re.match(r"[^@]+@[^@]+\.[^@]+", value)
#     )

# def safe_json(text):

#     try:

#         match = re.search(
#             r"\{.*\}",
#             text,
#             re.DOTALL
#         )

#         if match:

#             return json.loads(
#                 match.group()
#             )

#     except Exception as e:

#         log(f"JSON ERROR: {e}")

#     return {}

# def domain_from_url(url):

#     try:

#         return urlparse(url).netloc

#     except:

#         return ""

# # =========================================================
# # TAVILY
# # =========================================================

# def tavily_search(query):

#     global TAVILY_CALLS

#     TAVILY_CALLS += 1

#     log(f"TAVILY CALL #{TAVILY_CALLS}")

#     client = TavilyClient(
#         api_key=TAVILY_API_KEY
#     )

#     with Timer("Tavily Search"):

#         try:

#             return client.search(
#                 query=query,
#                 search_depth="advanced",
#                 max_results=15,
#                 include_answer=True,
#                 include_raw_content=True
#             )

#         except Exception as e:

#             log(f"TAVILY ERROR: {e}")

#             return {}

# # =========================================================
# # SERPAPI
# # =========================================================

# def serpapi_search(query):

#     global SERPAPI_CALLS

#     SERPAPI_CALLS += 1

#     log(f"SERPAPI CALL #{SERPAPI_CALLS}")

#     with Timer("SerpAPI Search"):

#         try:

#             params = {
#                 "engine": "google",
#                 "q": query,
#                 "num": 10,
#                 "api_key": SERPAPI_API_KEY
#             }

#             return GoogleSearch(
#                 params
#             ).get_dict()

#         except Exception as e:

#             log(f"SERPAPI ERROR: {e}")

#             return {}

# # =========================================================
# # MERGE RESULTS
# # =========================================================

# def merge_results(tavily_data, serpapi_data):

#     merged = []

#     for item in tavily_data.get("results", []):

#         merged.append({

#             "title": item.get("title"),

#             "url": item.get("url"),

#             "content": item.get("content"),

#             "source": "tavily"
#         })

#     for item in serpapi_data.get(
#         "organic_results",
#         []
#     ):

#         merged.append({

#             "title": item.get("title"),

#             "url": item.get("link"),

#             "content": item.get("snippet"),

#             "source": "serpapi"
#         })

#     log(f"TOTAL SEARCH RESULTS: {len(merged)}")

#     return merged

# # =========================================================
# # CRAWL4AI
# # =========================================================

# async def crawl_site(url):

#     try:

#         with Timer("Crawl4AI"):

#             async with AsyncWebCrawler() as crawler:

#                 result = await crawler.arun(
#                     url=url
#                 )

#                 return result.markdown

#     except Exception as e:

#         log(f"CRAWL ERROR: {e}")

#         return ""

# # =========================================================
# # APIFY LINKEDIN
# # =========================================================

# def linkedin_scraper(query):

#     global APIFY_CALLS

#     APIFY_CALLS += 1

#     log(f"APIFY CALL #{APIFY_CALLS}")

#     url = (
#         "https://api.apify.com/v2/acts/"
#         "apimaestro~linkedin-profile-scraper/"
#         "run-sync-get-dataset-items"
#     )

#     payload = {
#         "queries": [query],
#         "maxPagesPerQuery": 1
#     }

#     headers = {
#         "Authorization": f"Bearer {APIFY_API_KEY}"
#     }

#     try:

#         with Timer("Apify LinkedIn"):

#             response = requests.post(
#                 url,
#                 headers=headers,
#                 json=payload,
#                 timeout=120
#             )

#             return response.json()

#     except Exception as e:

#         log(f"APIFY ERROR: {e}")

#         return []

# # =========================================================
# # NEWS EXTRACTION
# # =========================================================

# def extract_news(url):

#     try:

#         article = Article(url)

#         article.download()

#         article.parse()

#         article.nlp()

#         return {

#             "title": article.title,

#             "summary": article.summary,

#             "date": str(article.publish_date),

#             "source": url,

#             "url": url
#         }

#     except:

#         return None

# # =========================================================
# # OLLAMA
# # =========================================================

# def ollama_json(prompt):

#     global OLLAMA_CALLS

#     OLLAMA_CALLS += 1

#     log(f"OLLAMA CALL #{OLLAMA_CALLS}")

#     with Timer("Ollama Extraction"):

#         response = llm.invoke(prompt)

#         return safe_json(response)

# # =========================================================
# # SAVE HELPERS
# # =========================================================

# def save_final_output(final_data):

#     filename = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

#     with open(filename, "w", encoding="utf-8") as f:

#         json.dump(final_data, f, indent=2, ensure_ascii=False)

#     log(f"FINAL OUTPUT SAVED -> {filename}")


# def save_raw_bundle(state):

#     raw_bundle = {
#         "query": state.get("query", ""),
#         "query_type": state.get("query_type", ""),
#         "search_results": state.get("search_results", []),
#         "linkedin_data": state.get("linkedin_data", {}),
#         "website_content": state.get("website_content", ""),
#         "company_data": state.get("company_data", {}),
#         "person_data": state.get("person_data", {}),
#         "news": state.get("news", []),
#         "final_output": state.get("final_output", {})
#     }

#     with open("raw.txt", "w", encoding="utf-8") as f:

#         f.write(json.dumps(raw_bundle, indent=2, ensure_ascii=False))

#     log("RAW DATA SAVED -> raw.txt")

# # =========================================================
# # CLASSIFIER
# # =========================================================

# def classify_node(state):

#     log("CLASSIFYING QUERY")

#     qtype = (
#         "person"
#         if is_email(state["query"])
#         else "company"
#     )

#     return {
#         **state,
#         "query_type": qtype
#     }

# # =========================================================
# # SEARCH
# # =========================================================

# def search_node(state):

#     log("SEARCHING COMPANY DATA")

#     query = state["query"]

#     tavily_data = tavily_search(query)

#     serp_data = serpapi_search(query)

#     merged = merge_results(
#         tavily_data,
#         serp_data
#     )

#     return {
#         **state,
#         "search_results": merged
#     }

# # =========================================================
# # WEBSITE SCRAPER
# # =========================================================

# def website_scraper_node(state):

#     log("SCRAPING WEBSITE")

#     website = None

#     for item in state["search_results"]:

#         url = item.get("url", "")

#         if (
#             "linkedin" not in url and
#             url.startswith("http")
#         ):

#             website = url

#             break

#     if not website:

#         return {
#             **state,
#             "website_content": ""
#         }

#     log(f"WEBSITE FOUND: {website}")

#     content = asyncio.run(
#         crawl_site(website)
#     )

#     return {
#         **state,
#         "website_content": content
#     }

# # =========================================================
# # LINKEDIN
# # =========================================================

# def linkedin_node(state):

#     log("SCRAPING LINKEDIN")

#     data = linkedin_scraper(
#         state["query"]
#     )

#     return {
#         **state,
#         "linkedin_data": data
#     }

# # =========================================================
# # MAIN ENRICHMENT AGENT
# # =========================================================

# def enrichment_agent(state):

#     log("RUNNING ENRICHMENT AGENT")

#     prompt = f"""
# You are a world-class enterprise enrichment AI.

# Extract COMPLETE and HIGH QUALITY data.

# RULES:
# - RETURN VALID JSON ONLY
# - NO MARKDOWN
# - NO EXPLANATION
# - USE PROVIDED SCHEMA EXACTLY
# - IF DATA UNKNOWN KEEP EMPTY
# - NEVER HALLUCINATE
# - FIND MAXIMUM DATA POSSIBLE

# IMPORTANT:

# 1. RELATED COMPANIES:
# Find companies:
# - same location
# - same industry
# - similar size
# - similar services

# 2. DECISION MAKERS:
# Find:
# - CEO
# - Founder
# - CTO
# - COO
# - VP
# - Directors

# 3. COMPETITORS:
# ONLY REAL COMPANIES

# 4. AI INSIGHTS:
# Generate:
# - growth stage
# - funding stage
# - confidence score
# - business health score

# SEARCH RESULTS:
# {json.dumps(state["search_results"])}

# WEBSITE:
# {state["website_content"]}

# LINKEDIN:
# {json.dumps(state["linkedin_data"])}

# OUTPUT SCHEMA:
# {json.dumps(FINAL_SCHEMA)}

# RETURN ONLY JSON.
# """

#     data = ollama_json(prompt)

#     return {
#         **state,
#         "company_data": data
#     }

# # =========================================================
# # NEWS AGENT
# # =========================================================

# def news_agent(state):

#     log("EXTRACTING NEWS")

#     news = []

#     for item in state["search_results"][:10]:

#         url = item.get("url")

#         if url:

#             extracted = extract_news(url)

#             if extracted:

#                 news.append(extracted)

#     log(f"NEWS COUNT: {len(news)}")

#     return {
#         **state,
#         "news": news
#     }

# # =========================================================
# # FINAL MERGE
# # =========================================================

# def final_merge(state):

#     log("MERGING FINAL OUTPUT")

#     final = FINAL_SCHEMA.copy()

#     enriched = state["company_data"]

#     if enriched:

#         for key, value in enriched.items():

#             final[key] = value

#     final["news"] = state["news"]

#     final["sources"] = [

#         "tavily",

#         "serpapi",

#         "crawl4ai",

#         "apify",

#         "newspaper3k",

#         "ollama"
#     ]

#     final["meta"]["last_updated"] = str(
#         datetime.now()
#     )

#     final["meta"]["data_completeness"] = 90

#     return {
#         **state,
#         "final_output": final
#     }

# # =========================================================
# # GRAPH
# # =========================================================

# graph = StateGraph(AgentState)

# graph.add_node(
#     "classify_node",
#     classify_node
# )

# graph.add_node(
#     "search_node",
#     search_node
# )

# graph.add_node(
#     "website_scraper_node",
#     website_scraper_node
# )

# graph.add_node(
#     "linkedin_node",
#     linkedin_node
# )

# graph.add_node(
#     "enrichment_agent",
#     enrichment_agent
# )

# graph.add_node(
#     "news_agent",
#     news_agent
# )

# graph.add_node(
#     "final_merge",
#     final_merge
# )

# graph.set_entry_point(
#     "classify_node"
# )

# graph.add_edge(
#     "classify_node",
#     "search_node"
# )

# graph.add_edge(
#     "search_node",
#     "website_scraper_node"
# )

# graph.add_edge(
#     "website_scraper_node",
#     "linkedin_node"
# )

# graph.add_edge(
#     "linkedin_node",
#     "enrichment_agent"
# )

# graph.add_edge(
#     "enrichment_agent",
#     "news_agent"
# )

# graph.add_edge(
#     "news_agent",
#     "final_merge"
# )

# graph.add_edge(
#     "final_merge",
#     END
# )

# app = graph.compile()

# # =========================================================
# # MAIN
# # =========================================================

# if __name__ == "__main__":

#     log("SYSTEM STARTED")

#     query = input(
#         "\nEnter company name or email: "
#     )

#     start = time.time()

#     result = app.invoke({

#         "query": query,

#         "query_type": "",

#         "search_results": [],

#         "linkedin_data": {},

#         "website_content": "",

#         "company_data": {},

#         "person_data": {},

#         "competitors": [],

#         "related_companies": [],

#         "news": [],

#         "final_output": {}
#     })

#     total = round(
#         time.time() - start,
#         2
#     )

#     print("\n")
#     print("=" * 80)
#     print("API STATS")
#     print("=" * 80)

#     print(f"TAVILY CALLS: {TAVILY_CALLS}")
#     print(f"SERPAPI CALLS: {SERPAPI_CALLS}")
#     print(f"APIFY CALLS: {APIFY_CALLS}")
#     print(f"OLLAMA CALLS: {OLLAMA_CALLS}")

#     print(f"\nTOTAL TIME: {total}s")

#     print("\n")
#     print("=" * 80)
#     print("FINAL OUTPUT")
#     print("=" * 80)

#     print(
#         json.dumps(
#             result["final_output"],
#             indent=2
#         )
#     )

#     save_final_output(result["final_output"])
#     save_raw_bundle(result)


# =========================================================
# ADVANCED COMPANY ENRICHMENT SYSTEM
# =========================================================

import os
import re
import time
import copy
import asyncio
import platform
from datetime import datetime
from typing import TypedDict, Dict, Any, List

import orjson
import requests
import tldextract
import trafilatura
import feedparser

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
except:
    FirecrawlApp = None

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

# =========================================================
# ENV
# =========================================================

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:14b"
)

# =========================================================
# LOGGER
# =========================================================

def log(msg):

    now = datetime.now().strftime("%H:%M:%S")

    print(f"\n[{now}] {msg}")

# =========================================================
# TIMER
# =========================================================

class Timer:

    def __init__(self, name):

        self.name = name

    def __enter__(self):

        self.start = time.time()

        log(f"STARTED: {self.name}")

    def __exit__(self, exc_type, exc_val, exc_tb):

        total = round(time.time() - self.start, 2)

        log(f"FINISHED: {self.name} ({total}s)")

# =========================================================
# API COUNTERS
# =========================================================

TAVILY_CALLS = 0
SERPAPI_CALLS = 0
APIFY_CALLS = 0
OLLAMA_CALLS = 0
FIRECRAWL_CALLS = 0

# =========================================================
# LLM
# =========================================================

llm = OllamaLLM(
    model=OLLAMA_MODEL,
    temperature=0
)

# =========================================================
# SCHEMA
# =========================================================

FINAL_SCHEMA = {

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

        "locations": [],

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

    "decision_makers": [],

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

        "competitors": [],

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

# =========================================================
# STATE
# =========================================================

class AgentState(TypedDict):

    query: str

    search_results: List[Dict[str, Any]]

    linkedin_data: Dict[str, Any]

    website_content: str

    firecrawl_content: str

    registry_data: Dict[str, Any]

    decision_makers_data: List[Dict[str, Any]]

    competitors_data: List[Dict[str, Any]]

    news_data: List[Dict[str, Any]]

    company_data: Dict[str, Any]

    final_output: Dict[str, Any]

# =========================================================
# HELPERS
# =========================================================

def dumps(data):

    return orjson.dumps(data).decode()

def safe_json(text):

    if isinstance(text, dict):
        return text

    try:

        match = re.search(
            r"\{.*\}",
            str(text),
            re.DOTALL
        )

        if match:

            return orjson.loads(
                match.group()
            )

    except Exception as e:

        log(f"JSON ERROR: {e}")

    return {}

def extract_domain(url):

    try:

        ext = tldextract.extract(url)

        return f"{ext.domain}.{ext.suffix}"

    except:
        return ""

def extract_emails(text):

    if not text:
        return []

    return list(set(re.findall(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        text
    )))

def extract_phones(text):

    if not text:
        return []

    phones = re.findall(
        r"(\+?\d[\d\s\-\(\)]{7,}\d)",
        text
    )

    cleaned = []

    for p in phones:

        p = re.sub(r"\s+", " ", p).strip()

        if len(re.sub(r"\D", "", p)) >= 8:
            cleaned.append(p)

    return list(dict.fromkeys(cleaned))

def deep_copy_schema():

    return copy.deepcopy(FINAL_SCHEMA)

# =========================================================
# SEARCH
# =========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1)
)
def tavily_search(query):

    global TAVILY_CALLS

    TAVILY_CALLS += 1

    log(f"TAVILY CALL #{TAVILY_CALLS}")

    client = TavilyClient(
        api_key=TAVILY_API_KEY
    )

    return client.search(
        query=query,
        search_depth="advanced",
        max_results=10,
        include_answer=True,
        include_raw_content=True
    )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1)
)
def serpapi_search(query):

    global SERPAPI_CALLS

    SERPAPI_CALLS += 1

    log(f"SERPAPI CALL #{SERPAPI_CALLS}")

    params = {

        "engine": "google",

        "q": query,

        "num": 10,

        "api_key": SERPAPI_API_KEY
    }

    return GoogleSearch(params).get_dict()

def merge_results(tavily_data, serpapi_data):

    merged = []

    for item in tavily_data.get("results", []):

        merged.append({

            "title": item.get("title", ""),

            "url": item.get("url", ""),

            "content": item.get("content", ""),

            "source": "tavily"
        })

    for item in serpapi_data.get(
        "organic_results",
        []
    ):

        merged.append({

            "title": item.get("title", ""),

            "url": item.get("link", ""),

            "content": item.get("snippet", ""),

            "source": "serpapi"
        })

    return merged

# =========================================================
# LINKEDIN HELPERS
# =========================================================

def linkedin_company_finder(company):

    query = f"site:linkedin.com/company {company}"

    data = serpapi_search(query)

    for item in data.get("organic_results", []):

        url = item.get("link", "")

        if "linkedin.com/company/" in url:
            return url

    return ""

def linkedin_scraper(query):

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

    payload = {

        "queries": [query],

        "maxPagesPerQuery": 1
    }

    headers = {

        "Authorization":
        f"Bearer {APIFY_API_KEY}"
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120
        )

        return response.json()

    except Exception as e:

        log(f"APIFY ERROR: {e}")

        return []

def enrich_linkedin_profile(url):

    data = linkedin_scraper(url)

    if isinstance(data, list) and data:
        return data[0]

    return {}

# =========================================================
# WEBSITE
# =========================================================

async def crawl_site(url):

    try:

        async with AsyncWebCrawler() as crawler:

            result = await crawler.arun(url=url)

            return result.markdown or ""

    except Exception as e:

        log(f"CRAWL ERROR: {e}")

        return ""

def firecrawl_scrape(url):

    global FIRECRAWL_CALLS

    if not FIRECRAWL_API_KEY:
        return ""

    try:

        FIRECRAWL_CALLS += 1

        app = FirecrawlApp(
            api_key=FIRECRAWL_API_KEY
        )

        result = app.scrape_url(
            url=url,
            formats=["markdown"]
        )

        return result.get("markdown", "")

    except Exception as e:

        log(f"FIRECRAWL ERROR: {e}")

        return ""

def extract_clean_text(url):

    try:

        downloaded = trafilatura.fetch_url(url)

        return trafilatura.extract(downloaded) or ""

    except:
        return ""

# =========================================================
# OLLAMA
# =========================================================

def ollama_json(prompt):

    global OLLAMA_CALLS

    OLLAMA_CALLS += 1

    log(f"OLLAMA CALL #{OLLAMA_CALLS}")

    response = llm.invoke(prompt)

    return safe_json(response)

# =========================================================
# SEARCH NODE
# =========================================================

def search_node(state):

    query = state["query"]

    tav = tavily_search(query)

    serp = serpapi_search(query)

    merged = merge_results(
        tav,
        serp
    )

    return {

        **state,

        "search_results": merged
    }

# =========================================================
# WEBSITE NODE
# =========================================================

def website_node(state):

    website = ""

    for item in state["search_results"]:

        url = item.get("url", "")

        if (
            url.startswith("http")
            and "linkedin" not in url
        ):

            website = url

            break

    if not website:

        return {

            **state,

            "website_content": ""
        }

    crawl4ai_content = asyncio.run(
        crawl_site(website)
    )

    firecrawl_content = firecrawl_scrape(
        website
    )

    trafilatura_content = extract_clean_text(
        website
    )

    merged_content = "\n\n".join([

        crawl4ai_content,

        firecrawl_content,

        trafilatura_content
    ])

    return {

        **state,

        "website_content": merged_content,

        "firecrawl_content": firecrawl_content
    }

# =========================================================
# REGISTRY NODE
# =========================================================

def registry_node(state):

    company = state["query"]

    queries = [

        f"{company} GST number",

        f"{company} GSTIN",

        f"{company} previous name",

        f"{company} formerly known as",

        f"{company} CIN number"
    ]

    results = []

    for q in queries:

        tav = tavily_search(q)

        serp = serpapi_search(q)

        results.extend(
            merge_results(tav, serp)
        )

    combined_text = dumps(results)

    gst = ""

    gst_match = re.findall(
        r"\b\d{2}[A-Z0-9]{13}\b",
        combined_text
    )

    if gst_match:
        gst = gst_match[0]

    previous_names = []

    prev_match = re.findall(
        r"(formerly known as|previously known as)(.*?)(\.|\n)",
        combined_text,
        re.I
    )

    for p in prev_match:

        previous_names.append(
            p[1].strip()
        )

    return {

        **state,

        "registry_data": {

            "GST_number": gst,

            "previous_names": list(
                dict.fromkeys(previous_names)
            )
        }
    }

# =========================================================
# LINKEDIN NODE
# =========================================================

def linkedin_node(state):

    company = state["query"]

    linkedin_url = linkedin_company_finder(
        company
    )

    linkedin_data = linkedin_scraper(
        company
    )

    return {

        **state,

        "linkedin_data": {

            "linkedin_url": linkedin_url,

            "profiles": linkedin_data
        }
    }

# =========================================================
# DECISION MAKER NODE
# =========================================================

def decision_maker_node(state):

    company = state["query"]

    searches = [

        f"site:linkedin.com/in {company} CEO",

        f"site:linkedin.com/in {company} Founder",

        f"site:linkedin.com/in {company} CTO",

        f"site:linkedin.com/in {company} COO",

        f"{company} leadership team"
    ]

    results = []

    for q in searches:

        data = serpapi_search(q)

        for item in data.get(
            "organic_results",
            []
        ):

            url = item.get("link", "")

            if "linkedin.com/in/" not in url:
                continue

            profile_data = enrich_linkedin_profile(
                url
            )

            results.append({

                "name": (
                    profile_data.get("fullName")
                    or item.get("title", "")
                ),

                "title": (
                    profile_data.get("headline")
                    or ""
                ),

                "linkedin_profile": url,

                "email": (
                    profile_data.get("email")
                    or ""
                ),

                "phone": (
                    profile_data.get("phone")
                    or ""
                ),

                "experience": (
                    profile_data.get("experiences")
                    or []
                ),

                "education": (
                    profile_data.get("education")
                    or []
                ),

                "professional_summary": (
                    profile_data.get("about")
                    or ""
                ),

                "source": "linkedin+apify"
            })

    deduped = []

    seen = set()

    for r in results:

        key = r["linkedin_profile"]

        if key in seen:
            continue

        seen.add(key)

        deduped.append(r)

    return {

        **state,

        "decision_makers_data": deduped[:10]
    }

# =========================================================
# COMPETITOR NODE
# =========================================================

def competitor_node(state):

    company = state["query"]

    company_data = state.get(
        "company_data",
        {}
    )

    industry = (
        company_data.get("company", {})
        .get("industry", "")
    )

    location = (
        company_data.get("company", {})
        .get("headquarters", {})
        .get("city", "")
    )

    size = (
        company_data.get("company", {})
        .get("company_size", "")
    )

    searches = [

        f"{company} competitors",

        f"{industry} companies {location}",

        f"{industry} companies {size}",

        f"companies similar to {company}"
    ]

    results = []

    for q in searches:

        serp = serpapi_search(q)

        results.extend(
            serp.get("organic_results", [])
        )

    prompt = f"""
Extract REAL competitors.

Need:
- name
- description
- website
- source

Rules:
- no hallucinations
- competitors should match location + company size + industry

Results:
{dumps(results)}

Return:
{{
  "competitors": []
}}
"""

    extracted = ollama_json(prompt)

    return {

        **state,

        "competitors_data":
        extracted.get("competitors", [])
    }

# =========================================================
# NEWS NODE
# =========================================================

def news_node(state):

    company = state["query"]

    news = []

    queries = [

        f"{company} latest news",

        f"{company} funding",

        f"{company} acquisition",

        f"{company} linkedin"
    ]

    for q in queries:

        serp = serpapi_search(q)

        for item in serp.get(
            "organic_results",
            []
        )[:5]:

            url = item.get("link", "")

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

                    "date": str(
                        article.publish_date
                    ),

                    "url": url
                })

            except:
                pass

    # =====================================================
    # LINKEDIN NEWS VIA RSS/GOOGLE
    # =====================================================

    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={company}+linkedin"
    )

    feed = feedparser.parse(rss_url)

    for entry in feed.entries[:10]:

        news.append({

            "title": entry.title,

            "summary": entry.get(
                "summary",
                ""
            ),

            "date": entry.get(
                "published",
                ""
            ),

            "url": entry.link
        })

    deduped = []

    seen = set()

    for n in news:

        key = n["title"]

        if key in seen:
            continue

        seen.add(key)

        deduped.append(n)

    return {

        **state,

        "news_data": deduped[:20]
    }

# =========================================================
# ENRICHMENT NODE
# =========================================================

def enrichment_node(state):

    prompt = f"""
You are a world-class company enrichment AI.

RULES:
- NEVER HALLUCINATE
- VALID JSON ONLY
- USE PROVIDED SCHEMA EXACTLY
- USE GST NUMBER FROM REGISTRY
- USE PREVIOUS NAMES
- USE LINKEDIN SCRAPED DATA
- USE DECISION MAKERS
- USE COMPETITOR DATA
- USE NEWS
- IF UNKNOWN KEEP EMPTY

SEARCH RESULTS:
{dumps(state["search_results"])}

WEBSITE:
{state["website_content"]}

LINKEDIN:
{dumps(state["linkedin_data"])}

REGISTRY:
{dumps(state["registry_data"])}

DECISION MAKERS:
{dumps(state["decision_makers_data"])}

COMPETITORS:
{dumps(state["competitors_data"])}

NEWS:
{dumps(state["news_data"])}

OUTPUT SCHEMA:
{dumps(FINAL_SCHEMA)}

RETURN ONLY JSON.
"""

    data = ollama_json(prompt)

    return {

        **state,

        "company_data": data
    }

# =========================================================
# FINAL REVIEW AGENT
# =========================================================

def final_review_agent(state):

    final = deep_copy_schema()

    enriched = state.get(
        "company_data",
        {}
    )

    if isinstance(enriched, dict):

        for k, v in enriched.items():

            final[k] = v

    # registry merge

    registry = state.get(
        "registry_data",
        {}
    )

    if registry.get("GST_number"):

        final["company"]["GST_number"] = (
            registry["GST_number"]
        )

    if registry.get("previous_names"):

        final["company"]["previous_names"] = (
            registry["previous_names"]
        )

    # linkedin merge

    linkedin = state.get(
        "linkedin_data",
        {}
    )

    if linkedin.get("linkedin_url"):

        final["company"]["linkedin"] = (
            linkedin["linkedin_url"]
        )

    # decision makers

    final["decision_makers"] = (
        state.get(
            "decision_makers_data",
            []
        )
    )

    # competitors

    final["market_intelligence"][
        "competitors"
    ] = state.get(
        "competitors_data",
        []
    )

    # news

    final["news"] = state.get(
        "news_data",
        []
    )

    # contact extraction

    website_text = state.get(
        "website_content",
        ""
    )

    emails = extract_emails(
        website_text
    )

    phones = extract_phones(
        website_text
    )

    if emails:

        final["company"]["contact"][
            "email"
        ] = emails[0]

    if phones:

        final["company"]["contact"][
            "phone"
        ] = phones[0]

    # domain

    website = (
        final["company"]
        .get("website", "")
    )

    if website:

        final["company"]["domain"] = (
            extract_domain(website)
        )

    # meta

    final["meta"]["last_updated"] = str(
        datetime.now()
    )

    final["sources"] = [

        "tavily",

        "serpapi",

        "crawl4ai",

        "firecrawl",

        "trafilatura",

        "linkedin",

        "apify",

        "rss",

        "ollama"
    ]

    # =====================================================
    # FINAL AI REVIEW
    # =====================================================

    review_prompt = f"""
You are the FINAL QUALITY REVIEW AGENT.

TASKS:
- fix structure
- remove duplicates
- improve formatting
- remove hallucinations
- normalize decision makers
- normalize competitors
- ensure valid json
- improve completeness
- fix invalid fields
- clean news
- ensure schema consistency

JSON:
{dumps(final)}

RETURN CLEAN JSON ONLY.
"""

    reviewed = ollama_json(
        review_prompt
    )

    if reviewed:
        final = reviewed

    filename = (
        f"output_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(filename, "wb") as f:

        f.write(

            orjson.dumps(
                final,
                option=orjson.OPT_INDENT_2
            )
        )

    log(f"FINAL JSON SAVED -> {filename}")

    return {

        **state,

        "final_output": final
    }

# =========================================================
# GRAPH
# =========================================================

graph = StateGraph(AgentState)

graph.add_node(
    "search_node",
    search_node
)

graph.add_node(
    "website_node",
    website_node
)

graph.add_node(
    "registry_node",
    registry_node
)

graph.add_node(
    "linkedin_node",
    linkedin_node
)

graph.add_node(
    "decision_maker_node",
    decision_maker_node
)

graph.add_node(
    "competitor_node",
    competitor_node
)

graph.add_node(
    "news_node",
    news_node
)

graph.add_node(
    "enrichment_node",
    enrichment_node
)

graph.add_node(
    "final_review_agent",
    final_review_agent
)

graph.set_entry_point(
    "search_node"
)

graph.add_edge(
    "search_node",
    "website_node"
)

graph.add_edge(
    "website_node",
    "registry_node"
)

graph.add_edge(
    "registry_node",
    "linkedin_node"
)

graph.add_edge(
    "linkedin_node",
    "decision_maker_node"
)

graph.add_edge(
    "decision_maker_node",
    "competitor_node"
)

graph.add_edge(
    "competitor_node",
    "news_node"
)

graph.add_edge(
    "news_node",
    "enrichment_node"
)

graph.add_edge(
    "enrichment_node",
    "final_review_agent"
)

graph.add_edge(
    "final_review_agent",
    END
)

app = graph.compile()

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    log("SYSTEM STARTED")

    query = input(
        "\nEnter company name: "
    ).strip()

    start = time.time()

    result = app.invoke({

        "query": query,

        "search_results": [],

        "linkedin_data": {},

        "website_content": "",

        "firecrawl_content": "",

        "registry_data": {},

        "decision_makers_data": [],

        "competitors_data": [],

        "news_data": [],

        "company_data": {},

        "final_output": {}
    })

    total_time = round(
        time.time() - start,
        2
    )

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

    print(

        orjson.dumps(
            result["final_output"],
            option=orjson.OPT_INDENT_2
        ).decode()
    )