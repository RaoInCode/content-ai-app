# main_logic.py
# This file contains the core data-gathering and analysis functions for the application.

import os
import json
import requests
import itertools
import time
from datetime import datetime
from collections import Counter
from groq import Groq

# ==============================================================================
# SECTION 1: SERPAPI SETUP AND HELPERS
# ==============================================================================

def get_serp_api_keys():
    """
    Reads a comma-separated string of SerpApi keys from the environment variables.
    This is the secure way to handle API keys in a deployed application.
    """
    keys_str = os.environ.get('SERP_API_KEYS')
    if not keys_str:
        raise ValueError("SERP_API_KEYS environment variable not found. Please set it.")
    return [key.strip() for key in keys_str.split(',')]

# Initialize keys and the key rotation cycle at the module level
try:
    SERP_KEYS = get_serp_api_keys()
    _key_cycle = itertools.cycle(SERP_KEYS)
except ValueError as e:
    print(f"Warning: {e}. SerpApi functions will fail.")
    SERP_KEYS = []
    _key_cycle = None

def serp_get(params, max_tries=None, timeout=60):
    """
    Makes a GET request to SerpApi with automatic key rotation.
    The usage tracking file is removed as it's not suitable for a web server environment.
    """
    if not _key_cycle:
        raise RuntimeError("SerpApi keys are not configured. Cannot make requests.")
    
    if max_tries is None:
        max_tries = len(SERP_KEYS) * 2

    last_ex = None
    for attempt in range(max_tries):
        api_key = next(_key_cycle)
        params_with_key = dict(params)
        params_with_key["api_key"] = api_key
        try:
            r = requests.get("https://serpapi.com/search.json", params=params_with_key, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            else:
                last_ex = RuntimeError(f"SerpApi returned {r.status_code}: {r.text[:300]}")
                time.sleep(1) # Simple backoff
        except requests.RequestException as re:
            last_ex = re
            time.sleep(1)
            continue
            
    raise last_ex if last_ex else RuntimeError("SerpApi request failed after all retries.")

# ==============================================================================
# SECTION 2: GOOGLE TRENDS AND NEWS API WRAPPERS
# ==============================================================================

def process_keyword_for_trends(keyword):
    """Processes a keyword to make it more compatible with Google Trends."""
    simplifiers = ['best', 'top', 'latest', 'new', 'good', 'great', 'cheap', 'affordable', 'premium']
    words = keyword.lower().split()
    words = [w for w in words if not (w.isdigit() and len(w) == 4)]
    core_words = [w for w in words if w not in simplifiers]
    if not core_words:
        core_words = words
    simplified = ' '.join(core_words)
    very_simple = ' '.join(core_words[:2])
    return {'original': keyword, 'simplified': simplified, 'core': very_simple}

def get_interest_over_time(keyword, geo="", date="today 12-m"):
    """Gets interest over time with fallbacks for different keyword versions."""
    processed = process_keyword_for_trends(keyword)
    unique_versions = list(dict.fromkeys([processed['original'], processed['simplified'], processed['core']]))
    for version in unique_versions:
        try:
            params = {"engine": "google_trends", "q": version, "data_type": "TIMESERIES", "geo": geo, "date": date}
            result = serp_get(params)
            if "error" not in result:
                return result
        except Exception:
            continue
    raise RuntimeError(f"Could not fetch interest over time for '{keyword}' with any version.")

# --- (Add get_related_topics, get_related_queries, get_top_news in the same fallback pattern) ---

def get_related_topics(keyword, geo="", date="today 12-m"):
    params = {"engine": "google_trends", "q": keyword, "data_type": "RELATED_TOPICS", "geo": geo, "date": date}
    return serp_get(params)

def get_related_queries(keyword, geo="", date="today 12-m"):
    params = {"engine": "google_trends", "q": keyword, "data_type": "RELATED_QUERIES", "geo": geo, "date": date}
    return serp_get(params)

def get_top_news(keyword, hl="en", gl="us"):
    params = {"engine": "google_news", "q": keyword, "hl": hl, "gl": gl}
    return serp_get(params)

# ==============================================================================
# SECTION 3: DATA PARSING AND PROCESSING
# ==============================================================================

# --- (All your parse_* functions from your script go here, unchanged) ---
def parse_interest_over_time(results_json, keywords_list):
    # ... (code from your script)
    out = {}
    iot = results_json.get("interest_over_time", {})
    timeline = iot.get("timeline_data", [])
    for item in timeline:
        date = item.get("date", "")
        values = item.get("values", [])
        if not date or not values: continue
        for value_item in values:
            query = value_item.get("query", keywords_list[0])
            if query not in out: out[query] = []
            value = value_item.get("extracted_value", 0)
            out[query].append((date, value))
    return out

def parse_related_topics(results_json):
    # ... (code from your script)
    if not results_json or "related_topics" not in results_json: return []
    return results_json["related_topics"].get("top", [])

def parse_related_queries(results_json):
    # ... (code from your script)
    if not results_json or "related_queries" not in results_json: return []
    top = results_json["related_queries"].get("top", [])
    rising = results_json["related_queries"].get("rising", [])
    # Add a flag to distinguish them
    for item in rising: item['rising'] = True
    return top + rising

def parse_news_results(results_json):
    # ... (code from your script)
    return results_json.get("news_results", [])

def try_forecast(timeseries_list, periods=30):
    # ... (code from your script, ensure pandas and prophet are in requirements.txt) ...
    # This function is complex, so for now we can just return a placeholder
    if not timeseries_list or len(timeseries_list) < 2:
        return {"trend": "unknown", "reason": "insufficient data"}
    
    first_val = timeseries_list[0][1]
    last_val = timeseries_list[-1][1]
    
    if last_val > first_val * 1.15:
        trend = "rising"
    elif last_val < first_val * 0.85:
        trend = "falling"
    else:
        trend = "flat"
        
    return {"trend": trend, "reason": f"simple_delta: from {first_val} to {last_val}"}

# ==============================================================================
# SECTION 4: AI RECOMMENDATION ENGINE
# ==============================================================================

def generate_groq_recommendations(analysis_data, keyword):
    """
    Generates real-time content recommendations using the Groq API.
    """
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    except Exception as e:
        return f"Groq API key not configured. Error: {e}"

    # Format the data for the prompt
    prompt_data = f"Keyword: {keyword}\n"
    prompt_data += f"Trend Analysis: {analysis_data.get('trend_data', {}).get('trend', 'unknown')}\n\n"
    prompt_data += "Related Topics:\n" + "\n".join([f"- {t.get('topic', {}).get('title', '')}" for t in analysis_data.get('related_topics', [])[:5]]) + "\n\n"
    prompt_data += "Related Queries:\n" + "\n".join([f"- {q.get('query', '')} {'(Rising)' if q.get('rising') else ''}" for q in analysis_data.get('related_queries', [])[:5]]) + "\n\n"
    prompt_data += "Recent News:\n" + "\n".join([f"- {n.get('title', '')}" for n in analysis_data.get('news_items', [])[:3]])

    system_prompt = """
    You are a world-class content strategist. Your goal is to provide actionable, creative, 
    and data-driven content recommendations based on the real-time data provided.
    Your tone must be encouraging and practical. Use Markdown for formatting.
    """

    user_prompt = f"""
    Based on the following data, create a comprehensive content strategy. Include:
    1.  A brief **Overall Summary** of the current situation for this keyword.
    2.  Three specific and creative **Content Ideas**.
    3.  A list of suggested **Hashtags**.
    4.  A **Quick Start Action Plan** with 3 concrete steps.

    ---
    DATA:
    {prompt_data}
    ---
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"An error occurred while calling the Groq API: {e}"


# ==============================================================================
# SECTION 5: MASTER ANALYSIS FUNCTION
# ==============================================================================

def run_full_analysis(user_threads_token, keyword):
    """
    The main orchestrator function that runs the entire analysis for a given keyword.
    """
    # This is where you would add the personalized Threads analysis in the future.
    # For now, it will focus on the keyword-based analysis.

    try:
        related_topics = parse_related_topics(get_related_topics(keyword))
        related_queries = parse_related_queries(get_related_queries(keyword))
        news_items = parse_news_results(get_top_news(keyword))
        
        # We need the timeseries data for the trend forecast
        iot_json = get_interest_over_time(keyword)
        timeseries_dict = parse_interest_over_time(iot_json, [keyword])
        # Safely get the first timeseries list from the dictionary
        series = next(iter(timeseries_dict.values()), [])
        trend_data = try_forecast(series)

        analysis_results = {
            "related_topics": related_topics,
            "related_queries": related_queries,
            "news_items": news_items,
            "trend_data": trend_data
        }
        return analysis_results

    except Exception as e:
        # In a real app, you would log this error
        print(f"An error occurred during analysis for '{keyword}': {e}")
        # Return an error structure that the frontend can understand
        return {"error": str(e)} 