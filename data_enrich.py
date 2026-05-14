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

