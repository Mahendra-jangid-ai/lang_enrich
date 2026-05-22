import os
import re
import json
import time
import copy
import asyncio
import platform

from concurrent.futures import ThreadPoolExecutor, as_completed
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

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "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")
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
# FINAL SCHEMA  (updated)
# =========================================================

FINAL_SCHEMA = {

    "person": {

        "first_name": "",

        "last_name": "",

        "full_name": "",

        "current_company": "",

        "current_role": "",

        "title": "",

        "department": "",

        "seniority_level": "",

        "description": "",

        "location": {

            "city": "",

            "state": "",

            "country": ""
        },

        "nationality": "",

        "residence_country": "",

        "contact": {

            "email": "",

            "phone": ""
        },

        "social": {

            "linkedin_url": ""
        },

        "experience": [

            {

                "company": "",

                "role_or_position": "",

                "start_date": "",

                "end_date": "",

                "duration": "",

                "location": ""
            }
        ],

        "meta": {

            "source": [],

            "confidence": 0
        }
    },

    "company": {

        "legal_name": "",

        "origin_country": "",

        "registration_number": "",

        "company_type": "",

        "status": "",

        "incorporation_date": "",

        "industry": "",

        "primary_sector": "",

        "sic_codes": [],

        "description": "",

        "company_size": "",

        "target_market_segment": "",

        "contact": {

            "website": "",

            "primary_email": "",

            "primary_phone": "",

            "headquarters": {

                "full_address": "",

                "address_line": "",

                "city": "",

                "state": "",

                "postal_code": "",

                "country": ""
            }
        },

        "social": {

            "linkedin_url": "",

            "glassdoor_url": "",

            "trustpilot_url": ""
        },

        "products_and_services": [

            {

                "name": "",

                "type": "",

                "description": "",

                "key_features": [],

                "target_audience": ""
            }
        ],

        "services": [],

        "products": []
    },

    "leadership": {

        "primary_decision_maker": {

            "name": "",

            "role": "",

            "title": "",

            "department": "",

            "nationality": "",

            "residence_country": "",

            "linkedin_url": "",

            "email": "",

            "phone": ""
        }
    },

    "business_intelligence": {

        "competitors": [

            {

                "name": "",

                "reason": "",

                "website": "",

                "industry": ""
            }
        ],

        "key_partnerships": [

            {

                "partner_name": "",

                "details": "",

                "source": "",

                "source_url": ""
            }
        ],

        "achievements": [],

        "recent_news": [

            {

                "title": "",

                "summary": "",

                "date": "",

                "source": "",

                "url": ""
            }
        ]
    },

    "links": {

        "official_websites": [],

        "other_useful_links": []
    },

    "metadata": {

        "data_confidence_score": 0,

        "sources_used": []
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
    # PERSON NAME
    # =====================================================

    cleaned = re.sub(r"\s+", " ", query).strip()

    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,60}", cleaned):

        parts = [p for p in cleaned.split(" ") if p]

        if 2 <= len(parts) <= 4:

            result["query_type"] = "person_name"

            result["person_name"] = cleaned

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


def parse_name_from_email(email):

    if not email or "@" not in email:
        return ""

    local = email.split("@", 1)[0]

    cleaned = re.sub(r"[._+-]+", " ", local).strip()

    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.title()


def is_executive_title(title):

    text = (title or "").lower()

    if not text:
        return False

    keywords = [
        "founder",
        "co-founder",
        "ceo",
        "chief",
        "managing director",
        "director",
        "owner",
        "president",
        "partner",
        "vp",
        "head"
    ]

    return any(k in text for k in keywords)


def normalize_alpha(text):

    return re.sub(r"[^a-z]", "", (text or "").lower())


def split_name_parts(name):

    parts = [
        normalize_alpha(p)
        for p in re.split(r"\s+", (name or "").strip())
    ]

    return [p for p in parts if p]


def extract_linkedin_person_slug(url):

    if not url:
        return ""

    match = re.search(r"linkedin\.com/in/([^/?#]+)", url, flags=re.IGNORECASE)

    if not match:
        return ""

    return match.group(1)


def linkedin_matches_name(url, name):

    slug = extract_linkedin_person_slug(url)

    if not slug or not name:
        return False

    slug_norm = normalize_alpha(slug)
    name_norm = normalize_alpha(name)

    if not slug_norm or not name_norm:
        return False

    parts = split_name_parts(name)

    if len(parts) >= 2:

        first = parts[0]
        last = parts[-1]

        if last not in slug_norm:
            return False

        if first in slug_norm:
            return True

        first_initial = first[0]

        if f"{first_initial}{last}" in slug_norm:
            return True

        if slug_norm.startswith(first_initial) and last in slug_norm:
            return True

        return False

    if slug_norm in name_norm or name_norm in slug_norm:
        return True

    return fuzz.ratio(slug_norm, name_norm) >= 90


def get_consistent_linkedin_url(person_record, candidates=None):

    if not person_record:
        return ""

    name = (person_record.get("name", "") or "").strip()

    direct_urls = [
        person_record.get("linkedin_url", ""),
        person_record.get("linkedin_profile", "")
    ]

    for url in direct_urls:
        if linkedin_matches_name(url, name):
            return url

    for candidate in candidates or []:

        cand_name = (candidate.get("name", "") or "").strip()

        if fuzz.ratio(normalize_alpha(cand_name), normalize_alpha(name)) < 88:
            continue

        urls = [
            candidate.get("linkedin_url", ""),
            candidate.get("linkedin_profile", "")
        ]

        for url in urls:
            if linkedin_matches_name(url, name):
                return url

    return ""


def pick_best_website(search_results, meta):

    company_domain = (meta.get("company_domain") or "").strip().lower()

    company_name = (meta.get("company_name") or "").strip().lower()

    blocked_domains = {
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "psuwatch.com"
    }

    best_url = ""
    best_score = -10**9

    for item in search_results:

        url = item.get("url", "")

        if not url.startswith("http"):
            continue

        if "linkedin" in url:
            continue

        domain = extract_domain(url).lower()

        if not domain:
            continue

        score = 0

        if domain in blocked_domains:
            score -= 200

        if company_domain and company_domain in domain:
            score += 400

        if company_name and company_name in domain:
            score += 180

        title = (item.get("title", "") or "").lower()
        content = (item.get("content", "") or "").lower()

        if company_name and (company_name in title or company_name in content):
            score += 80

        if any(x in url.lower() for x in ["/news", "/appointment", "/press", "/article"]):
            score -= 40

        if score > best_score:
            best_score = score
            best_url = url

    return best_url


def get_company_seed(state):

    meta = state.get("query_meta", {}) or {}

    query_type = meta.get("query_type", "")

    company_name = (meta.get("company_name") or "").strip()

    if company_name:
        return company_name

    enriched = state.get("company_data", {}) or {}

    if isinstance(enriched, dict):

        enriched_company = (
            enriched.get("company", {})
            .get("legal_name", "")
            .strip()
        )

        if enriched_company:
            return enriched_company

    for candidate in state.get("decision_makers_data", []) or []:

        current_company = (
            candidate.get("current_company", "")
            or candidate.get("company", "")
        )

        if current_company:
            return current_company.strip()

        for exp in candidate.get("experience", []) or []:

            exp_company = (exp.get("company", "") or "").strip()

            if exp_company:
                return exp_company

    if query_type in ["company", "company_website"]:
        return state.get("query", "").strip()

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

        "company.registration_number":
            f"{company} company registration number",

        "company.status":
            f"{company} company status",

        "company.company_type":
            f"{company} company type",

        "company.incorporation_date":
            f"{company} incorporation date",

        "company.origin_country":
            f"{company} country of origin",

        "company.contact.primary_email":
            f"{company} contact email",

        "company.contact.primary_phone":
            f"{company} contact phone",

        "leadership.primary_decision_maker.email":
            f"{company} founder CEO email",

        "leadership.primary_decision_maker.linkedin_url":
            f"{company} CEO founder linkedin",

        "person.contact.email":
            f"{company} founder email",

        "person.location.country":
            f"{company} founder location country"
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

    elif meta["query_type"] == "person_name":

        person_name = meta.get("person_name", raw_query)

        search_query = f'''
{person_name}
linkedin
current company
ceo
founder
profile
'''

    elif meta["query_type"] == "linkedin_person":

        search_query = f'''
{raw_query}
current company
role
leadership
'''

    else:

        search_query = company_query

    # =====================================================
    # PARALLEL: Tavily + SerpAPI simultaneously
    # OS Concept: Multi-threading via ThreadPoolExecutor
    # Both I/O-bound API calls run concurrently
    # =====================================================

    with ThreadPoolExecutor(max_workers=2) as executor:

        future_tavily = executor.submit(
            tavily_search,
            search_query
        )

        future_serp = executor.submit(
            serpapi_search,
            search_query
        )

        tavily_data = future_tavily.result()
        serp_data = future_serp.result()

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

    website = pick_best_website(
        state["search_results"],
        state.get("query_meta", {})
    )

    if not website:

        return {

            **state,

            "website_content": ""
        }

    log(f"WEBSITE FOUND: {website}")

    # =====================================================
    # PARALLEL: Crawl4AI + Trafilatura simultaneously
    # OS Concept: Async I/O (crawl4ai) + Thread (trafilatura)
    # =====================================================

    with ThreadPoolExecutor(max_workers=2) as executor:

        future_trafilatura = executor.submit(
            extract_clean_text,
            website
        )

        crawl4ai_content = asyncio.run(
            crawl_site(website)
        )

        trafilatura_content = future_trafilatura.result()

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

    company = get_company_seed(state)

    if not company:

        return {

            **state,

            "linkedin_data": {

                "linkedin_url": "",

                "profiles": []
            }
        }

    linkedin_company_query = (
        f"site:linkedin.com/company {company}"
    )

    # =====================================================
    # PARALLEL: LinkedIn SerpAPI + Apify scraper
    # OS Concept: Thread pool — both I/O-bound tasks
    # =====================================================

    with ThreadPoolExecutor(max_workers=2) as executor:

        future_serp = executor.submit(
            serpapi_search,
            linkedin_company_query
        )

        future_apify = executor.submit(
            linkedin_scraper,
            company
        )

        serp = future_serp.result()
        profiles = future_apify.result()

    linkedin_url = ""

    for item in serp.get(
        "organic_results",
        []
    ):

        url = item.get("link", "")

        if "linkedin.com/company/" in url:

            linkedin_url = url
            break

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

    meta = state.get("query_meta", {})

    query_type = meta.get("query_type", "company")

    company = get_company_seed(state)

    if query_type == "person_name":

        person = meta.get("person_name", state["query"])

        searches = [

            f'site:linkedin.com/in "{person}"',

            f'"{person}" linkedin profile',

            f'"{person}" current company',

            f'"{person}" CEO',

            f'"{person}" Founder',

            f'"{person}" director',

            f'"{person}" management team'
        ]

    else:

        company = company or state["query"]

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

    # =====================================================
    # PARALLEL: All decision maker searches at once
    # OS Concept: Thread pool with max_workers=6
    # Semaphore-like control via ThreadPoolExecutor limit
    # =====================================================

    results = []

    with ThreadPoolExecutor(max_workers=6) as executor:

        futures = {
            executor.submit(serpapi_search, q): q
            for q in searches
        }

        for future in as_completed(futures):

            try:

                data = future.result()

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

                        "query": futures[future]
                    })

            except Exception as e:

                log(f"DM SEARCH ERROR: {e}")

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

STRICT:
- prioritize CEO/Founder/Co-Founder/Director/VP/Head only
- reject random employees without decision authority
- if query_type is person_email/person_name/linkedin_person, do NOT return that person unless title is executive/founder

Need:
- name
- title
- linkedin_profile (as linkedin_url)
- email
- phone
- experience
- professional_summary
- source

Search Data:
{orjson.dumps(results).decode()}

Query Type:
{query_type}

Company Context:
{company}

Input Person:
{meta.get("person_name", "") or meta.get("person_email", "")}

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

    company = get_company_seed(state)

    if not company:

        return {

            **state,

            "competitors_data": []
        }

    searches = [

        f"{company} competitors",

        f"companies like {company}",

        f"{company} alternatives",

        f"top competitors of {company}",

        f"similar companies to {company}"
    ]

    # =====================================================
    # PARALLEL: All competitor searches at once
    # OS Concept: Thread pool — fan-out pattern
    # Each search is an independent I/O task
    # =====================================================

    results = []

    with ThreadPoolExecutor(max_workers=5) as executor:

        tav_futures = {
            executor.submit(tavily_search, q): q
            for q in searches
        }

        serp_futures = {
            executor.submit(serpapi_search, q): q
            for q in searches
        }

        all_futures = {**tav_futures, **serp_futures}

        for future in as_completed(all_futures):

            try:

                data = future.result()

                # tavily returns dict with "results"
                # serpapi returns dict with "organic_results"
                # merge_results handles both cleanly

                if "results" in data:

                    results.extend(
                        merge_results(data, {})
                    )

                elif "organic_results" in data:

                    results.extend(
                        merge_results({}, data)
                    )

            except Exception as e:

                log(f"COMPETITOR SEARCH ERROR: {e}")

    prompt = f"""
You are a competitive intelligence AI.

Find REAL competitors only.

Rules:
- no fake companies
- valid JSON only
- include website
- include short description/reason
- include industry
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
      "reason": "",
      "website": "",
      "industry": ""
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

1. LEADERSHIP
Need:
- primary_decision_maker (CEO / Founder)
  - name, role, title, department
  - nationality, residence_country
  - linkedin_url, email, phone

2. BUSINESS INTELLIGENCE
Need:
- competitors (name, reason, website, industry)
- key_partnerships
- achievements
- recent_news (title, summary, date, source, url)

3. COMPANY
Need:
- legal_name, origin_country
- registration_number, company_type, status
- incorporation_date, industry, primary_sector
- sic_codes, description, company_size
- target_market_segment
- contact: website, primary_email, primary_phone
- headquarters: full_address, address_line, city,
  state, postal_code, country
- social: linkedin_url, glassdoor_url, trustpilot_url
- products_and_services, services, products

4. LINKS
Need:
- official_websites []
- other_useful_links []

5. METADATA
Need:
- data_confidence_score (0-100)
- sources_used []

SEARCH RESULTS:
{orjson.dumps(state['search_results']).decode()}

QUERY META:
{orjson.dumps(state['query_meta']).decode()}

IMPORTANT QUERY HANDLING:
- If query_type is person_name, linkedin_person, or person_email:
    - Fill ONLY person fields for that specific person.
    - Fill company/business/links/leadership based on that person's current company,
        not from the person's name text.
- Never treat a person's name as a company name.

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

    query_meta = state.get("query_meta", {}) or {}
    query_type = query_meta.get("query_type", "")

    company_seed = get_company_seed(state)

    if not company_seed:
        return {
            **state,
            "news": []
        }

    blocked_keywords = {
        "appointment",
        "biography",
        "profile",
        "cv",
        "resume",
        "psu",
        "government",
        "ministry"
    }

    if query_type in ["person_name", "person_email", "linkedin_person"]:

        company_news_query = f"{company_seed} news"

        with ThreadPoolExecutor(max_workers=2) as executor:

            f_tav = executor.submit(tavily_search, company_news_query)
            f_serp = executor.submit(serpapi_search, company_news_query)

            tav_data = f_tav.result()
            serp_data = f_serp.result()

        search_results = merge_results(tav_data, serp_data)

        urls = []
        for item in search_results:

            url = item.get("url", "")
            title = (item.get("title", "") or "").lower()
            content = (item.get("content", "") or "").lower()

            if any(keyword in title or keyword in content for keyword in blocked_keywords):
                continue

            if "linkedin.com/in/" in url:
                continue

            urls.append(url)

        urls = list(dict.fromkeys(urls))[:10]

    else:

        urls = [
            item.get("url")
            for item in state["search_results"][:10]
            if item.get("url") and "linkedin.com/in/" not in item.get("url", "")
        ]

    # =====================================================
    # PARALLEL: Scrape company news articles
    # OS Concept: Thread pool — I/O-bound parallel fetch
    # Each Article download is independent network call
    # =====================================================

    def fetch_article(url):

        try:

            article = Article(url)

            article.download()

            article.parse()

            article.nlp()

            return {

                "title": article.title,

                "summary": article.summary,

                "date": str(article.publish_date),

                "source": url,

                "url": url,

                "post_type": "news_article"
            }

        except:
            return None

    news = []

    with ThreadPoolExecutor(max_workers=5) as executor:

        futures = {
            executor.submit(fetch_article, url): url
            for url in urls
        }

        for future in as_completed(futures):

            result = future.result()

            if result:
                news.append(result)

    # =====================================================
    # LINKEDIN POSTS: Fetch company posts + posts about company
    # =====================================================

    linkedin_posts = []

    try:

        linkedin_company_query = f'site:linkedin.com/company "{company_seed}"'

        with ThreadPoolExecutor(max_workers=2) as executor:

            f_tav = executor.submit(tavily_search, linkedin_company_query)
            f_serp = executor.submit(serpapi_search, linkedin_company_query)

            tav_posts = f_tav.result()
            serp_posts = f_serp.result()

        post_results = merge_results(tav_posts, serp_posts)

        for item in post_results[:15]:

            try:

                post_url = item.get("url", "")

                if "linkedin.com" not in post_url:
                    continue

                post_title = item.get("title", "")
                post_content = item.get("content", "")
                post_date = item.get("published_at") or item.get("date", "")

                author = ""
                if "linkedin.com/in/" in post_url:
                    author = "user"
                    post_type = "person_post_about_company"
                else:
                    author = company_seed
                    post_type = "company_post"

                linkedin_posts.append({

                    "title": post_title,

                    "summary": post_content[:500] if post_content else post_title,

                    "date": str(post_date) if post_date else "",

                    "source": post_url,

                    "url": post_url,

                    "author": author,

                    "post_type": post_type
                })

            except:
                continue

    except:
        pass

    # =====================================================
    # MERGE & SORT: Combine news articles + LinkedIn posts
    # Sort by date in ASCENDING order (oldest to recent)
    # =====================================================

    all_news = news + linkedin_posts

    def parse_date(date_str):
        if not date_str or date_str == "None":
            return None
        try:
            from datetime import datetime
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d")
            except:
                return None

    all_news_sorted = sorted(
        [item for item in all_news if parse_date(item.get("date")) is not None],
        key=lambda x: parse_date(x.get("date")) or datetime.now()
    )

    return {

        **state,

        "news": all_news_sorted
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

    # =====================================================
    # MAP DECISION MAKERS -> LEADERSHIP
    # =====================================================

    decision_makers = state.get(
        "decision_makers_data",
        []
    )

    query_meta = state.get("query_meta", {}) or {}

    query_type = query_meta.get("query_type", "")

    target_person_name = query_meta.get("person_name", "").strip()
    target_person_email = query_meta.get("person_email", "").strip().lower()

    if not target_person_name and target_person_email:
        target_person_name = parse_name_from_email(target_person_email)

    company_seed = get_company_seed(state).lower()

    selected_leader = None

    if decision_makers:

        best_leader_score = -10**9

        for candidate in decision_makers:

            name = (candidate.get("name", "") or "").strip()
            role_text = (
                candidate.get("title", "")
                or candidate.get("role", "")
            )

            score = 0

            if is_executive_title(role_text):
                score += 120

            candidate_company = (
                candidate.get("current_company", "")
                or candidate.get("company", "")
            ).lower()

            if company_seed and candidate_company and company_seed in candidate_company:
                score += 40

            if candidate.get("linkedin_url") or candidate.get("linkedin_profile"):
                score += 10

            if target_person_name and query_type in ["person_name", "person_email", "linkedin_person"]:
                name_score = fuzz.ratio(
                    target_person_name.lower(),
                    name.lower()
                )

                if name_score >= 90 and not is_executive_title(role_text):
                    score -= 200

            if score > best_leader_score:
                best_leader_score = score
                selected_leader = candidate

    if selected_leader:

        leader_linkedin = get_consistent_linkedin_url(
            selected_leader,
            decision_makers
        )

        final["leadership"]["primary_decision_maker"] = {

            "name": selected_leader.get("name", ""),

            "role": selected_leader.get(
                "role",
                selected_leader.get("title", "")
            ),

            "title": selected_leader.get("title", ""),

            "department": selected_leader.get("department", ""),

            "nationality": selected_leader.get("nationality", ""),

            "residence_country": selected_leader.get(
                "residence_country", ""
            ),

            "linkedin_url": leader_linkedin,

            "email": selected_leader.get("email", ""),

            "phone": selected_leader.get("phone", "")
        }

    selected_person = None

    if query_type in ["person_name", "person_email", "linkedin_person"] and decision_makers:

        if target_person_email:
            for candidate in decision_makers:
                cand_email = (candidate.get("email", "") or "").strip().lower()
                if cand_email and cand_email == target_person_email:
                    selected_person = candidate
                    break

        if not selected_person and target_person_name:

            best_person_score = -1

            for candidate in decision_makers:
                cand_name = (candidate.get("name", "") or "").strip().lower()

                score = fuzz.ratio(target_person_name.lower(), cand_name)

                if score > best_person_score:
                    best_person_score = score
                    selected_person = candidate

            if best_person_score < 70:
                selected_person = None

    if selected_person:

        person_linkedin = get_consistent_linkedin_url(
            selected_person,
            decision_makers
        )

        person_full_name = selected_person.get("name", "")

        name_parts = [p for p in person_full_name.split() if p]

        final["person"]["full_name"] = person_full_name

        if name_parts:
            final["person"]["first_name"] = name_parts[0]

        if len(name_parts) > 1:
            final["person"]["last_name"] = " ".join(name_parts[1:])

        final["person"]["current_company"] = (
            selected_person.get("current_company", "")
            or selected_person.get("company", "")
        )

        final["person"]["current_role"] = selected_person.get("title", "")

        final["person"]["title"] = selected_person.get("title", "")

        final["person"]["department"] = selected_person.get("department", "")

        final["person"]["description"] = selected_person.get(
            "professional_summary",
            ""
        )

        final["person"]["nationality"] = selected_person.get("nationality", "")

        final["person"]["residence_country"] = selected_person.get(
            "residence_country",
            ""
        )

        final["person"]["contact"]["email"] = selected_person.get("email", "")

        final["person"]["contact"]["phone"] = selected_person.get("phone", "")

        final["person"]["social"]["linkedin_url"] = person_linkedin

        exp = selected_person.get("experience", [])

        if isinstance(exp, list) and exp:
            final["person"]["experience"] = exp

    elif query_type == "person_email" and target_person_email:

        final["person"]["contact"]["email"] = target_person_email

        if target_person_name:
            parts = [p for p in target_person_name.split() if p]
            final["person"]["full_name"] = target_person_name

            if parts:
                final["person"]["first_name"] = parts[0]
            if len(parts) > 1:
                final["person"]["last_name"] = " ".join(parts[1:])

    # =====================================================
    # MAP COMPETITORS -> BUSINESS INTELLIGENCE
    # =====================================================

    final["business_intelligence"][
        "competitors"
    ] = state.get(
        "competitors_data",
        []
    )

    # =====================================================
    # EXTRACT EMAILS + PHONES FROM WEBSITE
    # =====================================================

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
            "primary_email"
        ] = emails[0]

    if phones:

        final["company"]["contact"][
            "primary_phone"
        ] = phones[0]

    # =====================================================
    # MAP NEWS -> BUSINESS INTELLIGENCE RECENT NEWS
    # =====================================================

    final["business_intelligence"][
        "recent_news"
    ] = state.get(
        "news",
        []
    )

    # =====================================================
    # LINKS
    # =====================================================

    website = final["company"]["contact"].get(
        "website",
        ""
    )

    if website:

        final["links"]["official_websites"] = [website]

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

                    set_nested_value(
                        final,
                        field,
                        value
                    )

    # =====================================================
    # STILL EMPTY => HYPOTHESIS SEARCH (PARALLEL)
    # OS Concept: Thread pool fan-out for hypothesis queries
    # Each field gets its own search thread simultaneously
    # =====================================================

    all_remaining = find_empty_fields(final)

    remaining_empty = []

    for field in all_remaining:

        if (

            field.startswith("company.")

            or

            field.startswith("leadership.")

            or

            field.startswith("business_intelligence.")

            or

            field.startswith("links.")
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
        ""
    ) or get_company_seed(state)

    def hypothesis_search(field):

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

            with ThreadPoolExecutor(
                max_workers=2
            ) as inner_exec:

                f_tav = inner_exec.submit(
                    tavily_search,
                    hypothesis_query
                )

                f_serp = inner_exec.submit(
                    serpapi_search,
                    hypothesis_query
                )

                tav = f_tav.result()
                serp = f_serp.result()

            search_data = merge_results(tav, serp)

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

            response = ollama_json(prompt)

            return field, response.get("value", "")

        except Exception as e:

            log(f"HYPOTHESIS ERROR: {e}")

            return field, ""

    with ThreadPoolExecutor(
        max_workers=4
    ) as executor:

        futures = {
            executor.submit(
                hypothesis_search, field
            ): field
            for field in remaining_empty
        }

        for future in as_completed(futures):

            field, value = future.result()

            if value not in EMPTY_VALUES:

                set_nested_value(
                    final,
                    field,
                    value
                )

    # =====================================================
    # METADATA
    # =====================================================

    final["metadata"]["sources_used"] = [

        "tavily",

        "serpapi",

        "crawl4ai",

        "apify",

        "newspaper3k",

        "ollama"
    ]

    final["metadata"][
        "data_confidence_score"
    ] = 95

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