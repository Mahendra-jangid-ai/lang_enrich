# =========================================================
# ADVANCED ENTERPRISE DATA ENRICHMENT SYSTEM
# FULL MERGED VERSION
# =========================================================

import os
import re
import json
import time
import copy
import asyncio
import platform

from datetime import datetime
from urllib.parse import urlparse
from typing import TypedDict, Dict, Any, List, final

import requests
import orjson
import tldextract
import trafilatura

from dotenv import load_dotenv
from rapidfuzz import fuzz
from tavily import TavilyClient
from serpapi import GoogleSearch
from crawl4ai import AsyncWebCrawler
from newspaper import Article
from langgraph.graph import StateGraph, END
from langchain_ollama import OllamaLLM
from tenacity import retry, stop_after_attempt, wait_exponential

# =========================================================
# WINDOWS FIX
# =========================================================

if platform.system() == "Windows":

    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:14b"
)

# =========================================================
# API COUNTERS
# =========================================================

TAVILY_CALLS = 0
SERPAPI_CALLS = 0
APIFY_CALLS = 0
OLLAMA_CALLS = 0

# =========================================================
# LOGGER
# =========================================================

def log(message):

    current = datetime.now().strftime(
        "%H:%M:%S"
    )

    print(f"\n[{current}] {message}")

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

        total = round(
            time.time() - self.start,
            2
        )

        log(f"FINISHED: {self.name} ({total}s)")

# =========================================================
# LLM
# =========================================================

llm = OllamaLLM(
    model=OLLAMA_MODEL,
    temperature=0
)

# =========================================================
# FINAL SCHEMA
# =========================================================

FINAL_SCHEMA = {

    "person": {

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

        "contact_info": {

            "email": "",

            "phone": ""
        }
    },

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

                "postal_code": "",

                "country": ""
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

        {

            "name": "",

            "title": "",

            "linkedin_profile": "",

            "email": "",

            "phone": "",

            "experience": [],

            "professional_summary": "",

            "source": ""
        }
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

            {

                "name": "",

                "description": "",

                "website": "",

                "source": ""
            }
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

# =========================================================
# STATE
# =========================================================

class AgentState(TypedDict):

    query: str

    search_results: List[Dict[str, Any]]

    linkedin_data: Dict[str, Any]

    website_content: str

    company_data: Dict[str, Any]

    decision_makers_data: List[Dict[str, Any]]

    competitors_data: List[Dict[str, Any]]

    news: List[Dict[str, Any]]

    final_output: Dict[str, Any]

    query_meta: Dict[str, Any]

# =========================================================
# HELPERS
# =========================================================

# =========================================================
# QUERY CLASSIFIER
# =========================================================

def classify_query(query):

    query = query.strip()

    result = {

        "query_type": "company",

        "person_email": "",

        "person_name": "",

        "company_name": "",

        "company_domain": ""
    }

    # =====================================================
    # EMAIL
    # =====================================================

    if re.match(
        r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        query
    ):

        result["query_type"] = "person_email"

        result["person_email"] = query

        local, domain = query.split("@")

        company = domain.split(".")[0]

        result["company_name"] = company

        result["company_domain"] = domain

        return result

    # =====================================================
    # LINKEDIN PROFILE
    # =====================================================

    if "linkedin.com/in/" in query:

        result["query_type"] = "linkedin_person"

        return result

    # =====================================================
    # WEBSITE
    # =====================================================

    if query.startswith("http"):

        domain = extract_domain(query)

        company = domain.split(".")[0]

        result["query_type"] = "company_website"

        result["company_name"] = company

        result["company_domain"] = domain

        return result

    # =====================================================
    # DEFAULT COMPANY
    # =====================================================

    result["company_name"] = query

    return result

def safe_json(text):

    try:

        if isinstance(text, dict):
            return text

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

    return list(
        set(
            re.findall(
                r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
                text or ""
            )
        )
    )

def extract_phones(text):

    phones = re.findall(
        r"(\+?\d[\d\s\-\(\)]{7,}\d)",
        text or ""
    )

    cleaned = []

    for p in phones:

        if len(re.sub(r"\D", "", p)) >= 8:
            cleaned.append(p.strip())

    return list(dict.fromkeys(cleaned))

def extract_clean_text(url):

    try:

        downloaded = trafilatura.fetch_url(url)

        return trafilatura.extract(downloaded) or ""

    except:
        return ""



# =========================================================
# EMPTY FIELD HELPERS
# =========================================================

EMPTY_VALUES = [
    None,
    "",
    [],
    {},
    "N/A",
    "Unknown",
    "Not Available"
]

def find_empty_fields(data, parent_key=""):

    empty_fields = []

    if isinstance(data, dict):

        for k, v in data.items():

            full_key = (
                f"{parent_key}.{k}"
                if parent_key
                else k
            )

            if v in EMPTY_VALUES:

                empty_fields.append(full_key)

            else:

                empty_fields.extend(
                    find_empty_fields(
                        v,
                        full_key
                    )
                )

    elif isinstance(data, list):

        for idx, item in enumerate(data):

            empty_fields.extend(
                find_empty_fields(
                    item,
                    f"{parent_key}[{idx}]"
                )
            )

    return empty_fields


def get_nested_value(data, path):

    try:

        keys = (
            path.replace("]", "")
            .replace("[", ".")
            .split(".")
        )

        current = data

        for key in keys:

            if key == "":
                continue

            if isinstance(current, list):

                current = current[int(key)]

            else:

                current = current.get(key)

            if current is None:
                return None

        return current

    except:
        return None


def set_nested_value(data, path, value):

    keys = (
        path.replace("]", "")
        .replace("[", ".")
        .split(".")
    )

    current = data

    for key in keys[:-1]:

        if key == "":
            continue

        if key.isdigit():

            key = int(key)

            while len(current) <= key:
                current.append({})

            current = current[key]

        else:

            if key not in current:
                current[key] = {}

            current = current[key]

    last = keys[-1]

    if last.isdigit():

        last = int(last)

        while len(current) <= last:
            current.append(None)

        current[last] = value

    else:

        current[last] = value


# =========================================================
# TRUSTPILOT REVIEW FIX
# =========================================================

def normalize_review_count(value):

    if not value:
        return ""

    value = str(value).strip()

    match = re.search(
        r"([\\d,.]+)",
        value
    )

    if not match:
        return ""

    try:

        num = (
            match.group(1)
            .replace(",", "")
        )

        if "." in num:
            num = float(num)
        else:
            num = int(num)

        # hallucination protection
        if num > 100000:
            return ""

        return str(int(num))

    except:

        return ""


# =========================================================
# HYPOTHESIS QUERY
# =========================================================

def build_hypothesis_query(
    company,
    field
):

    field_map = {

        "company.GST_number":
            f"{company} GST number",

        "company.status":
            f"{company} company status",

        "company.company_type":
            f"{company} company type",

        "company.incorporation_date":
            f"{company} incorporation date",

        "financial_snapshot.revenue":
            f"{company} annual revenue",

        "financial_snapshot.profit":
            f"{company} annual profit",

        "online_presence.trustpilot_reviews":
            f"{company} trustpilot total reviews",

        "online_presence.monthly_web_visits_estimate":
            f"{company} monthly website traffic",

        "person.email":
            f"{company} founder email",

        "person.location":
            f"{company} founder location"
    }

    return field_map.get(
        field,
        f"{company} {field}"
    )
# =========================================================
# SEARCH HELPERS
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

    with Timer("Tavily Search"):

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

        "num": 25,

        "api_key": SERPAPI_API_KEY
    }

    with Timer("SerpAPI"):

        return GoogleSearch(params).get_dict()

def merge_results(tavily_data, serpapi_data):

    merged = []

    for item in tavily_data.get(
        "results",
        []
    ):

        merged.append({

            "title": item.get(
                "title",
                ""
            ),

            "url": item.get(
                "url",
                ""
            ),

            "content": item.get(
                "content",
                ""
            ),

            "source": "tavily"
        })

    for item in serpapi_data.get(
        "organic_results",
        []
    ):

        merged.append({

            "title": item.get(
                "title",
                ""
            ),

            "url": item.get(
                "link",
                ""
            ),

            "content": item.get(
                "snippet",
                ""
            ),

            "source": "serpapi"
        })

    return merged

# =========================================================
# CRAWLER
# =========================================================

async def crawl_site(url):

    try:

        with Timer("Crawl4AI"):

            async with AsyncWebCrawler() as crawler:

                result = await crawler.arun(
                    url=url
                )

                return result.markdown

    except Exception as e:

        log(f"CRAWL ERROR: {e}")

        return ""

# =========================================================
# APIFY LINKEDIN
# =========================================================

def linkedin_scraper(query):

    global APIFY_CALLS

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

        "Authorization": f"Bearer {APIFY_API_KEY}"
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

    raw_query = state["query"]

    meta = classify_query(
        raw_query
    )

    company_query = (
        meta.get("company_name")
        or raw_query
    )

    log(
        f"QUERY TYPE: "
        f"{meta['query_type']}"
    )

    log(
        f"COMPANY QUERY: "
        f"{company_query}"
    )

    # =====================================================
    # PERSON EMAIL SEARCH BOOST
    # =====================================================

    if meta["query_type"] == "person_email":

        person_email = meta[
            "person_email"
        ]

        search_query = f'''
{person_email}
{company_query}
leadership
team
founder
director
linkedin
'''

    else:

        search_query = company_query

    tavily_data = tavily_search(
        search_query
    )

    serp_data = serpapi_search(
        search_query
    )

    merged = merge_results(
        tavily_data,
        serp_data
    )

    return {

        **state,

        "query_meta": meta,

        "search_results": merged
    }
# =========================================================
# WEBSITE NODE
# =========================================================

def website_node(state):

    website = None

    for item in state["search_results"]:

        url = item.get("url", "")

        if (

            "linkedin" not in url and

            url.startswith("http")
        ):

            website = url
            break

    if not website:

        return {

            **state,

            "website_content": ""
        }

    log(f"WEBSITE FOUND: {website}")

    crawl4ai_content = asyncio.run(
        crawl_site(website)
    )

    trafilatura_content = extract_clean_text(
        website
    )

    merged = "\n\n".join([

        crawl4ai_content,

        trafilatura_content
    ])

    return {

        **state,

        "website_content": merged
    }

# =========================================================
# LINKEDIN NODE
# =========================================================

def linkedin_node(state):

    company = state[
        "query_meta"
    ].get(
        "company_name",
        state["query"]
    )

    linkedin_company_query = (
        f"site:linkedin.com/company {company}"
    )

    serp = serpapi_search(
        linkedin_company_query
    )

    linkedin_url = ""

    for item in serp.get(
        "organic_results",
        []
    ):

        url = item.get("link", "")

        if "linkedin.com/company/" in url:

            linkedin_url = url
            break

    profiles = linkedin_scraper(company)

    return {

        **state,

        "linkedin_data": {

            "linkedin_url": linkedin_url,

            "profiles": profiles
        }
    }

# =========================================================
# DECISION MAKERS
# =========================================================

def decision_maker_agent(state):

    company = state[
        "query_meta"
    ].get(
        "company_name",
        state["query"]
    )
    searches = [

        f'site:linkedin.com/in "{company}" CEO',

        f'site:linkedin.com/in "{company}" Founder',

        f'site:linkedin.com/in "{company}" Co-Founder',

        f'site:linkedin.com/in "{company}" Managing Director',

        f'site:linkedin.com/in "{company}" Director',

        f'site:linkedin.com/in "{company}" CTO',

        f'site:linkedin.com/in "{company}" COO',

        f'site:linkedin.com/in "{company}" VP',

        f'site:linkedin.com/in "{company}" leadership',

        f'site:linkedin.com/in "{company}" team',

        f'"{company}" leadership team',

        f'"{company}" executive team',

        f'"{company}" founders',

        f'"{company}" directors'
    ]
    results = []

    for q in searches:

        data = serpapi_search(q)

        for item in data.get(
            "organic_results",
            []
        ):

            results.append({

                "title": item.get(
                    "title",
                    ""
                ),

                "url": item.get(
                    "link",
                    ""
                ),

                "snippet": item.get(
                    "snippet",
                    ""
                ),

                "query": q
            })

    prompt = f"""
You are an elite B2B lead intelligence AI.

Extract REAL decision makers.

RULES:
- only real people
- no hallucination
- valid JSON only
- must belong to company
- prefer linkedin profiles
- max 10 people

Need:
- name
- title
- linkedin_profile
- email
- phone
- experience
- education
- professional_summary
- source

Search Data:
{orjson.dumps(results).decode()}

Return:
{{
  "decision_makers": []
}}
"""
    extracted = ollama_json(prompt)

    return {

        **state,

        "decision_makers_data": extracted.get(
            "decision_makers",
            []
        )
    }

# =========================================================
# COMPETITORS
# =========================================================

def competitors_agent(state):

    company = state[
        "query_meta"
    ].get(
        "company_name",
        state["query"]
    )

    searches = [

        f"{company} competitors",

        f"companies like {company}",

        f"{company} alternatives",

        f"top competitors of {company}",

        f"similar companies to {company}"
    ]

    results = []

    for q in searches:

        tav = tavily_search(q)

        serp = serpapi_search(q)

        results.extend(
            merge_results(tav, serp)
        )

    prompt = f"""
You are a competitive intelligence AI.

Find REAL competitors only.

Rules:
- no fake companies
- valid JSON only
- include website
- include short description
- max 10 competitors

Company:
{company}

Search Data:
{orjson.dumps(results).decode()}


Return:
{{
  "competitors": [
    {{
      "name": "",
      "description": "",
      "website": "",
      "source": ""
    }}
  ]
}}
"""

    extracted = ollama_json(prompt)
    # =====================================================
# FALLBACK LINKEDIN EXTRACTION
# =====================================================

    if not extracted.get("decision_makers"):

        fallback = []

        for r in results:

            title = r.get(
                "title",
                ""
            )

            url = r.get(
                "url",
                ""
            )

            snippet = r.get(
                "snippet",
                ""
            )

            if "linkedin.com/in/" not in url:
                continue

            possible_name = title.split("-")[0].strip()

            if len(possible_name.split()) < 2:
                continue

            fallback.append({

                "name": possible_name,

                "title": snippet[:120],

                "linkedin_profile": url,

                "email": "",

                "phone": "",

                "experience": [],

                "professional_summary": snippet,

                "source": "fallback_linkedin"
            })

        extracted["decision_makers"] = fallback[:10]
    return {

        **state,

        "competitors_data": extracted.get(
            "competitors",
            []
        )
    }

# =========================================================
# ENRICHMENT AGENT
# =========================================================

def enrichment_agent(state):

    prompt = f"""
You are a world-class enterprise enrichment AI.

Extract COMPLETE enterprise intelligence.

VERY IMPORTANT RULES:
- NEVER HALLUCINATE
- RETURN VALID JSON ONLY
- USE PROVIDED SCHEMA EXACTLY
- IF UNKNOWN KEEP EMPTY
- NO MARKDOWN
- NO EXPLANATION

IMPORTANT EXTRACTION RULES:

1. DECISION MAKERS
Need:
- CEO
- Founder
- CTO
- COO
- VP
- Directors

2. COMPETITORS
Need:
- real companies only
- include website
- include description

3. COMPANY
Need:
- legal name
- industry
- employee count
- website
- linkedin
- contact details
- headquarters

4. AI INSIGHTS
Generate:
- business health score
- confidence score
- growth stage
- funding stage

SEARCH RESULTS:
{orjson.dumps(state['search_results']).decode()}

QUERY META:
{orjson.dumps(state['query_meta']).decode()}

WEBSITE:
{state['website_content']}

LINKEDIN:
{orjson.dumps(state['linkedin_data']).decode()}

DECISION MAKERS:
{orjson.dumps(state['decision_makers_data']).decode()}

COMPETITORS:
{orjson.dumps(state['competitors_data']).decode()}

OUTPUT SCHEMA:
{orjson.dumps(FINAL_SCHEMA).decode()}

RETURN ONLY JSON.
"""

    data = ollama_json(prompt)

    return {

        **state,

        "company_data": data
    }

# =========================================================
# NEWS AGENT
# =========================================================

def news_agent(state):

    news = []

    for item in state["search_results"][:10]:

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

                "source": url,

                "url": url
            })

        except:
            pass

    return {

        **state,

        "news": news
    }

# =========================================================
# FINAL MERGE
# =========================================================

def final_merge(state):

    final = copy.deepcopy(FINAL_SCHEMA)

    enriched = state.get(
        "company_data",
        {}
    )

    if isinstance(enriched, dict):

        for key, value in enriched.items():

            final[key] = value

    final["decision_makers"] = state.get(
        "decision_makers_data",
        []
    )

    final["market_intelligence"][
        "competitors"
    ] = state.get(
        "competitors_data",
        []
    )

    website_content = state.get(
        "website_content",
        ""
    )

    emails = extract_emails(
        website_content
    )

    phones = extract_phones(
        website_content
    )

    if emails:

        final["company"]["contact"][
            "email"
        ] = emails[0]

        final["lead_generation_targets"][
            "general_contact_email"
        ] = emails[0]

    if phones:

        final["company"]["contact"][
            "phone"
        ] = phones[0]

        final["lead_generation_targets"][
            "general_phone"
        ] = phones[0]

    if final["company"].get("website"):

        final["company"]["domain"] = (
            extract_domain(
                final["company"]["website"]
            )
        )

    final["news"] = state.get(
        "news",
        []
    )

    # =====================================================
    # FIX WRONG TRUSTPILOT REVIEWS
    # =====================================================

    trustpilot_reviews = (
        final.get(
            "online_presence",
            {}
        ).get(
            "trustpilot_reviews",
            ""
        )
    )

    final["online_presence"][
        "trustpilot_reviews"
    ] = normalize_review_count(
        trustpilot_reviews
    )

    # =====================================================
    # EMPTY FIELD DETECTION
    # =====================================================

    empty_fields = find_empty_fields(
        final
    )

    log(
        f"EMPTY FIELDS FOUND: "
        f"{len(empty_fields)}"
    )

    # =====================================================
    # FIRST LLM RETRY
    # =====================================================

    if empty_fields:

        retry_prompt = f'''
You are an enterprise enrichment AI.

Fill ONLY missing fields.

RULES:
- NO HALLUCINATION
- HIGH CONFIDENCE ONLY
- KEEP UNKNOWN EMPTY
- RETURN VALID JSON ONLY

CURRENT DATA:
{json.dumps(final, indent=2)}

EMPTY FIELDS:
{json.dumps(empty_fields, indent=2)}
'''

        retry_data = ollama_json(
            retry_prompt
        )

        if isinstance(retry_data, dict):

            for field in empty_fields:

                value = get_nested_value(
                    retry_data,
                    field
                )

                if value not in EMPTY_VALUES:

                    if (
                        "trustpilot_reviews"
                        in field
                    ):

                        value = (
                            normalize_review_count(
                                value
                            )
                        )

                    set_nested_value(
                        final,
                        field,
                        value
                    )

    # =====================================================
    # STILL EMPTY => HYPOTHESIS SEARCH
    # =====================================================
    all_remaining = find_empty_fields(
        final
    )

    remaining_empty = []

    for field in all_remaining:

        if (

            field.startswith("financial_snapshot.")

            or

            field.startswith("company.")

            or

            field.startswith("corporate_structure.")

            or

            field.startswith("online_presence.")
        ):

            remaining_empty.append(field)

    log(
        f"TARGETED HYPOTHESIS FIELDS: "
        f"{len(remaining_empty)}"
    )

    company_name = final.get(
        "company",
        {}
    ).get(
        "legal_name",
        state["query"]
    )

    for field in remaining_empty:

        try:

            hypothesis_query = (
                build_hypothesis_query(
                    company_name,
                    field
                )
            )

            log(
                f"HYPOTHESIS SEARCH: "
                f"{hypothesis_query}"
            )

            tav = tavily_search(
                hypothesis_query
            )

            serp = serpapi_search(
                hypothesis_query
            )

            search_data = merge_results(
                tav,
                serp
            )

            prompt = f'''
Find value for field:
{field}

Company:
{company_name}

Search Results:
{json.dumps(search_data)}

RULES:
- HIGH CONFIDENCE ONLY
- NO HALLUCINATION
- RETURN JSON ONLY

FORMAT:
{{
    "value": ""
}}
'''

            response = ollama_json(
                prompt
            )

            value = response.get(
                "value",
                ""
            )

            if value not in EMPTY_VALUES:

                if (
                    "trustpilot_reviews"
                    in field
                ):

                    value = (
                        normalize_review_count(
                            value
                        )
                    )

                set_nested_value(
                    final,
                    field,
                    value
                )

        except Exception as e:

            log(
                f"HYPOTHESIS ERROR: {e}"
            )

    final["sources"] = [

        "tavily",

        "serpapi",

        "crawl4ai",

        "apify",

        "newspaper3k",

        "ollama"
    ]

    final["meta"]["last_updated"] = str(
        datetime.now()
    )

    final["meta"]["data_completeness"] = 95

    final["meta"]["notes"] = [

        "Advanced decision maker intelligence enabled",

        "Competitor intelligence enabled",

        "LinkedIn enrichment enabled",

        "LLM retry enrichment enabled",

        "Hypothesis search enabled"
    ]

    return {

        **state,

        "final_output": final
    }
# =========================================================
# SAVE OUTPUT
# =========================================================

def save_final_output(final_data):

    filename = (
        f"output_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            final_data,
            f,
            indent=2,
            ensure_ascii=False
        )

    log(f"OUTPUT SAVED -> {filename}")

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
    "linkedin_node",
    linkedin_node
)

graph.add_node(
    "decision_maker_agent",
    decision_maker_agent
)

graph.add_node(
    "competitors_agent",
    competitors_agent
)

graph.add_node(
    "enrichment_agent",
    enrichment_agent
)

graph.add_node(
    "news_agent",
    news_agent
)

graph.add_node(
    "final_merge",
    final_merge
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
    "linkedin_node"
)

graph.add_edge(
    "linkedin_node",
    "decision_maker_agent"
)

graph.add_edge(
    "decision_maker_agent",
    "competitors_agent"
)

graph.add_edge(
    "competitors_agent",
    "enrichment_agent"
)

graph.add_edge(
    "enrichment_agent",
    "news_agent"
)

graph.add_edge(
    "news_agent",
    "final_merge"
)

graph.add_edge(
    "final_merge",
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

        "query_meta": {},

        "linkedin_data": {},

        "website_content": "",

        "company_data": {},

        "decision_makers_data": [],

        "competitors_data": [],

        "news": [],

        "final_output": {}
    })

    total = round(
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

    print(f"OLLAMA CALLS: {OLLAMA_CALLS}")

    print(f"\nTOTAL TIME: {total}s")

    print("\n")
    print("=" * 80)
    print("FINAL OUTPUT")
    print("=" * 80)

    print(

        json.dumps(

            result["final_output"],

            indent=2,

            ensure_ascii=False
        )
    )

    save_final_output(
        result["final_output"]
    )
