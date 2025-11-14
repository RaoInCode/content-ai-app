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
import concurrent.futures 
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ==============================================================================
# SECTION 1: SERPAPI SETUP AND HELPERS
# ==============================================================================

def get_key_for_service(service_name):
    """
    Retrieves the dedicated key for a specific service (forecast, topics, queries, news).
    Falls back to the main rotation if the specific key is missing.
    """
    env_var_map = {
        "forecast": "SERP_API_KEY_FORECAST",
        "topics": "SERP_API_KEY_TOPICS",
        "queries": "SERP_API_KEY_QUERIES",
        "news": "SERP_API_KEY_NEWS"
    }
    
    specific_key = os.environ.get(env_var_map.get(service_name))
    if specific_key:
        return specific_key
    
    # Fallback to main rotation
    if _key_cycle:
        return next(_key_cycle)
    
    return None

# Initialize main fallback keys
try:
    keys_str = os.environ.get('SERP_API_KEYS')
    SERP_KEYS = [k.strip() for k in keys_str.split(',')] if keys_str else []
    _key_cycle = itertools.cycle(SERP_KEYS) if SERP_KEYS else None
except Exception:
    SERP_KEYS = []
    _key_cycle = None

def serp_get(params, api_key=None, timeout=120):
    """
    Makes a GET request to SerpApi using a specific key.
    """
    if not api_key:
        if _key_cycle:
            api_key = next(_key_cycle)
        else:
            print("Error: No SerpApi key available for this request.")
            return {"error": "No API key"}

    params_with_key = dict(params)
    params_with_key["api_key"] = api_key
    
    try:
        # We use a dedicated key, so we can retry a few times on that same key if needed
        for attempt in range(3):
            try:
                r = requests.get("https://serpapi.com/search.json", params=params_with_key, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                else:
                    print(f"SerpApi Attempt {attempt+1} failed: {r.status_code}")
                    time.sleep(1)
            except requests.RequestException:
                time.sleep(1)
                continue
        return {"error": "Request failed after retries"}
    except Exception as e:
        return {"error": str(e)}

# ==============================================================================
# SECTION 2: GOOGLE TRENDS AND NEWS WRAPPERS
# ==============================================================================

def process_keyword_for_trends(keyword):
    simplifiers = ['best', 'top', 'latest', 'new', 'good', 'great', 'cheap', 'affordable', 'premium']
    words = keyword.lower().split()
    words = [w for w in words if not (w.isdigit() and len(w) == 4)]
    core_words = [w for w in words if w not in simplifiers]
    if not core_words: core_words = words
    simplified = ' '.join(core_words)
    very_simple = ' '.join(core_words[:2])
    return {'original': keyword, 'simplified': simplified, 'core': very_simple}

# --- API CALL FUNCTIONS (Now accept an explicit API key) ---

def fetch_interest_over_time_raw(keyword, api_key, geo="", date="today 12-m"):
    processed = process_keyword_for_trends(keyword)
    # Try variations if original fails, but keep it simple for this worker
    unique_versions = list(dict.fromkeys([processed['original'], processed['simplified'], processed['core']]))
    
    for version in unique_versions:
        params = {"engine": "google_trends", "q": version, "data_type": "TIMESERIES", "geo": geo, "date": date}
        result = serp_get(params, api_key=api_key)
        if "error" not in result and "interest_over_time" in result:
            return result
            
    return {"error": "Could not fetch interest over time"}

def fetch_related_topics_raw(keyword, api_key, geo="", date="today 12-m"):
    params = {"engine": "google_trends", "q": keyword, "data_type": "RELATED_TOPICS", "geo": geo, "date": date}
    return serp_get(params, api_key=api_key)

def fetch_related_queries_raw(keyword, api_key, geo="", date="today 12-m"):
    params = {"engine": "google_trends", "q": keyword, "data_type": "RELATED_QUERIES", "geo": geo, "date": date}
    return serp_get(params, api_key=api_key)

def fetch_top_news_raw(keyword, api_key, hl="en", gl="us"):
    params = {"engine": "google_news", "q": keyword, "hl": hl, "gl": gl}
    return serp_get(params, api_key=api_key)

# ==============================================================================
# SECTION 3: DATA PARSING
# ==============================================================================

def parse_interest_over_time(results_json, keyword):
    out = {}
    if not results_json or "error" in results_json: return out
    iot = results_json.get("interest_over_time", {})
    timeline = iot.get("timeline_data", [])
    for item in timeline:
        date = item.get("date", "")
        values = item.get("values", [])
        if not date or not values: continue
        for value_item in values:
            # Just grab the extracted value
            val = value_item.get("extracted_value", 0)
            if keyword not in out: out[keyword] = []
            out[keyword].append((date, val))
    return out

# def parse_related_topics(results_json):
#     if not results_json or "related_topics" not in results_json: return []
#     raw_topics = results_json["related_topics"].get("top", [])
#     clean_topics = []
#     for item in raw_topics:
#         if "topic" in item:
#             clean_topics.append({
#                 "title": item["topic"].get("title", "Unknown"),
#                 "type": item["topic"].get("type", "Topic"),
#                 "value": item.get("value", "")
#             })
#     return clean_topics

def parse_related_topics(results_json):
    """
    Robust parser that handles both nested and flat topic structures.
    """
    if not results_json or "related_topics" not in results_json: return []
    
    # Trends often puts data in 'top' or 'rising'. We check both.
    raw_topics = results_json["related_topics"].get("top", [])
    if not raw_topics:
        raw_topics = results_json["related_topics"].get("rising", [])

    clean_topics = []
    
    for item in raw_topics:
        # Case 1: Nested structure (standard) -> item['topic']['title']
        if "topic" in item:
            clean_topics.append({
                "title": item["topic"].get("title", "Unknown"),
                "type": item["topic"].get("type", "Topic"),
                "value": item.get("value", "")
            })
        # Case 2: Flat structure (sometimes returned) -> item['title']
        elif "title" in item:
             clean_topics.append({
                "title": item.get("title", "Unknown"),
                "type": item.get("type", "Topic"),
                "value": item.get("value", "")
            })
            
    return clean_topics

# def parse_related_queries(results_json):
#     if not results_json or "related_queries" not in results_json: return []
#     top = results_json["related_queries"].get("top", [])
#     rising = results_json["related_queries"].get("rising", [])
#     for item in rising: item['rising'] = True
#     return top + rising

def parse_related_queries(results_json):
    """
    Robust parser for queries.
    """
    if not results_json or "related_queries" not in results_json: return []
    
    # Combine top and rising queries
    top = results_json["related_queries"].get("top", [])
    rising = results_json["related_queries"].get("rising", [])
    
    # Ensure they have the right keys for frontend
    cleaned = []
    for item in top + rising:
        if "query" in item:
            cleaned.append({
                "query": item["query"],
                "rising": item.get("rising", False) # Preserve rising flag if present
            })
            
    return cleaned

def parse_news_results(results_json):
    if not results_json: return []
    raw_news = results_json.get("news_results", [])
    clean_news = []
    for item in raw_news:
        link = item.get("link")
        if not link: continue
        source_raw = item.get("source", "Unknown")
        source = source_raw.get("name", "Unknown") if isinstance(source_raw, dict) else str(source_raw)
        clean_news.append({
            "title": item.get("title", "No Title"),
            "link": link,
            "source": source,
            "date": item.get("date", "")
        })
    return clean_news

def try_forecast(timeseries_list):
    if not timeseries_list or len(timeseries_list) < 2:
        return {"trend": "unknown", "reason": "insufficient data"}
    first_val = timeseries_list[0][1]
    last_val = timeseries_list[-1][1]
    if last_val > first_val * 1.15: trend = "rising"
    elif last_val < first_val * 0.85: trend = "falling"
    else: trend = "flat"
    return {"trend": trend, "reason": f"simple_delta: from {first_val} to {last_val}"}

# ==============================================================================
# SECTION 4: AI RECOMMENDATION ENGINE
# ==============================================================================

def generate_groq_recommendations(analysis_data, keyword):
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    except Exception as e:
        return f"Groq API key not configured. Error: {e}"

    prompt_data = f"Keyword: {keyword}\n"
    prompt_data += f"Trend Analysis: {analysis_data.get('trend_data', {}).get('trend', 'unknown')}\n\n"
    
    # Extract titles for prompt
    topics_str = "\n".join([f"- {t.get('title', '')}" for t in analysis_data.get('related_topics', [])[:5]])
    prompt_data += f"Related Topics:\n{topics_str}\n\n"
    
    queries_str = "\n".join([f"- {q.get('query', '')} {'(Rising)' if q.get('rising') else ''}" for q in analysis_data.get('related_queries', [])[:5]])
    prompt_data += f"Related Queries:\n{queries_str}\n\n"
    
    news_str = "\n".join([f"- {n.get('title', '')}" for n in analysis_data.get('news_items', [])[:3]])
    prompt_data += f"Recent News:\n{news_str}"

    system_prompt = "You are a world-class content strategist. Use Markdown."
    user_prompt = f"""
    Based on the following data, create a comprehensive content strategy. Include:
    1. Overall Summary
    2. Three specific Content Ideas
    3. Suggested Hashtags
    4. Quick Start Action Plan (3 steps)
    ---
    DATA:
    {prompt_data}
    ---
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"An error occurred while calling the Groq API: {e}"

# ==============================================================================
# SECTION 5: MASTER ANALYSIS FUNCTION (4-WORKER PARALLEL EXECUTION)
# ==============================================================================

def worker_forecast(keyword):
    key = get_key_for_service("forecast")
    try:
        raw = fetch_interest_over_time_raw(keyword, key)
        parsed = parse_interest_over_time(raw, keyword)
        # Get the first available timeseries
        series = next(iter(parsed.values()), [])
        return try_forecast(series)
    except Exception as e:
        print(f"Forecast Worker Failed: {e}")
        return {"trend": "unknown", "reason": "error"}

def worker_topics(keyword):
    key = get_key_for_service("topics")
    try:
        raw = fetch_related_topics_raw(keyword, key)
        return parse_related_topics(raw)
    except Exception as e:
        print(f"Topics Worker Failed: {e}")
        return []

# def worker_queries(keyword):
#     key = get_key_for_service("queries")
#     try:
#         raw = fetch_related_queries_raw(keyword, key)
#         return parse_related_queries(raw)
#     except Exception as e:
#         print(f"Queries Worker Failed: {e}")
#         return []
    
def worker_queries(keyword):
    key = get_key_for_service("queries")
    print(f"🔍 DEBUG: Fetching Queries for '{keyword}' using key ...{str(key)[-5:]}")
    
    try:
        raw = fetch_related_queries_raw(keyword, key)
        
        # --- NEW DEBUGGING BLOCK ---
        if isinstance(raw, dict) and "error" in raw:
            print(f"❌ API ERROR (Queries): {raw['error']}")
            return []
            
        if isinstance(raw, dict) and "related_queries" not in raw:
            print(f"⚠️ MISSING DATA (Queries): API returned valid JSON but no 'related_queries'.")
            print(f"   Available keys: {list(raw.keys())}")
            # If Google Trends is just empty, this is normal.
            return []
        # ---------------------------

        return parse_related_queries(raw)
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in Queries Worker: {e}")
        return []

def worker_news(keyword):
    key = get_key_for_service("news")
    try:
        raw = fetch_top_news_raw(keyword, key)
        return parse_news_results(raw)
    except Exception as e:
        print(f"News Worker Failed: {e}")
        return []

def run_full_analysis(user_threads_token, keyword):
    """
    Runs 4 distinct workers in parallel using 4 separate keys (if available).
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Launch all 4 tasks simultaneously
            f_trend = executor.submit(worker_forecast, keyword)
            f_topics = executor.submit(worker_topics, keyword)
            f_queries = executor.submit(worker_queries, keyword)
            f_news = executor.submit(worker_news, keyword)
            
            # Collect results (each handles its own errors, so this won't crash)
            trend_data = f_trend.result()
            related_topics = f_topics.result()
            related_queries = f_queries.result()
            news_items = f_news.result()

        analysis_results = {
            "keyword": keyword,
            "related_topics": related_topics,
            "related_queries": related_queries,
            "trend_data": trend_data,
            "news_items": news_items 
        }
        return analysis_results

    except Exception as e:
        print(f"An error occurred during parallel analysis: {e}")
        return {"error": str(e)}

# ==============================================================================
# SECTION 6: THREADS API & SENTIMENT (Fully Restored)
# ==============================================================================

def get_threads_profile(access_token):
    url = "https://graph.threads.net/v1.0/me"
    params = {"fields": "id,username,name,threads_profile_picture_url,threads_biography", "access_token": access_token}
    try:
        return requests.get(url, params=params, timeout=15).json()
    except Exception:
        return {"error": "Invalid response from Threads API"}

def fetch_user_threads(access_token, limit=3, since=None, until="now"):
    profile = get_threads_profile(access_token)
    user_id = profile.get("id")
    if not user_id: return {"error": "Could not fetch Threads user id", "profile": profile}
    
    params = {
        "fields": "id,text,permalink,timestamp,media_product_type,media_type", 
        "limit": limit, 
        "access_token": access_token
    }
    if since: params["since"] = since
    if until and until != "now": params["until"] = until
    
    url = f"https://graph.threads.net/v1.0/{user_id}/threads"
    try:
        r = requests.get(url, params=params, timeout=20)
        out = r.json()
        out["_profile"] = profile
        return out
    except Exception:
        return {"error": "Invalid response from Threads API"}

def fetch_replies(access_token, post_id, reverse=True):
    params = {"fields": "id,text,username,timestamp", "access_token": access_token}
    if reverse: params["reverse"] = "true"
    url = f"https://graph.threads.net/v1.0/{post_id}/replies"
    try:
        return requests.get(url, params=params, timeout=20).json()
    except Exception:
        return {"error": "Invalid response from Threads API"}

# def analyze_replies_sentiment(replies_list):
#     HF_API = os.environ.get("HF_API_KEY")
#     if not HF_API:
#         return {"per_reply": [], "overall_sentiment": "Error: HF_API_KEY missing", "cumulative_sentiment": 0.0}

#     headers = {"Authorization": f"Bearer {HF_API}"}
#     api_url = "https://api-inference.huggingface.co/models/cardiffnlp/twitter-xlm-roberta-base-sentiment"
    
#     per_reply, sentiments_vals = [], []
    
#     for reply in replies_list:
#         text = reply.get("text", "")
#         if not text.strip(): continue
#         try:
#             res = requests.post(api_url, headers=headers, json={"inputs": text}, timeout=30).json()
#             if isinstance(res, list) and res:
#                 top = max(res[0], key=lambda x: x['score'])
#                 label = top['label'].upper()
#                 score = top['score']
#             else:
#                 label, score = "ERROR", 0.0
            
#             polarity = score if "POS" in label else (-score if "NEG" in label else 0.0)
#             sentiments_vals.append(polarity)
#             per_reply.append({"username": reply.get("username"), "text": text, "label": label, "score": score})
#         except Exception as e:
#             per_reply.append({"text": text, "error": str(e)})

#     if not sentiments_vals:
#         return {"per_reply": per_reply, "overall_sentiment": "No Text", "cumulative_sentiment": 0.0}

#     cumulative = sum(sentiments_vals) / len(sentiments_vals)
#     if cumulative > 0.2: overall = "Overall Positive"
#     elif cumulative < -0.2: overall = "Overall Negative"
#     else: overall = "Overall Neutral"
    
#     recommendations = ["Use the recommendations page!"]
#     if overall == "Overall Positive": recommendations = ["Keep doing what you're doing!"]
    
#     return {
#         "per_reply": per_reply,
#         "cumulative_sentiment": cumulative,
#         "overall_sentiment": overall,
#         "recommendations": recommendations
#     }

# def analyze_replies_sentiment(replies_list):
#     """
#     Offload sentiment analysis to Hugging Face Inference API.
#     UPDATED: Uses a social-media specific model that supports Neutral sentiment.
#     """
#     HF_API = os.environ.get("HF_API_KEY")
    
#     if not HF_API:
#         print("❌ DEBUG: HF_API_KEY is missing.")
#         return {
#             "per_reply": [],
#             "cumulative_sentiment": 0.0,
#             "overall_sentiment": "Error: HF_API_KEY missing",
#             "recommendations": ["Please configure HF_API_KEY in environment variables."]
#         }

#     headers = {"Authorization": f"Bearer {HF_API}"}
    
#     # SWITCHING TO A ROBUST SOCIAL MEDIA MODEL (Twitter-Roberta)
#     # This model understands emojis and slang better
#     api_url = "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest"
    
#     per_reply = []
#     sentiments_vals = []

#     print(f"🔍 DEBUG: Analyzing {len(replies_list)} replies...")

#     for reply in replies_list:
#         text = reply.get("text", "")
#         if not text.strip(): continue

#         try:
#             # Increased timeout slightly to 20s for the heavier model
#             response = requests.post(api_url, headers=headers, json={"inputs": text}, timeout=20)
            
#             if response.status_code != 200:
#                 print(f"❌ HF API Error: {response.status_code} - {response.text}")
#                 per_reply.append({
#                     "username": reply.get("username"), 
#                     "text": text, 
#                     "label": f"API Error {response.status_code}", 
#                     "score": 0.0
#                 })
#                 continue

#             result = response.json()
            
#             # Parse the response (Handle [[{label: 'positive', score: 0.9}]] format)
#             if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
#                 top = max(result[0], key=lambda x: x['score'])
#                 label_raw = top['label'].lower() # Normalize to lowercase
#                 score = float(top['score'])
#             else:
#                 print(f"⚠️ Unexpected JSON format: {result}")
#                 label_raw = "error"
#                 score = 0.0

#             # Calculate Polarity (Positive=1, Negative=-1, Neutral=0)
#             polarity = 0.0
#             label_display = label_raw.upper() # For display

#             if "positive" in label_raw:
#                 polarity = score
#             elif "negative" in label_raw:
#                 polarity = -score
#             else:
#                 # Neutral case
#                 polarity = 0.0
#                 label_display = "NEUTRAL"

#             # Only count valid scores
#             if "error" not in label_raw:
#                 sentiments_vals.append(polarity)

#             per_reply.append({
#                 "username": reply.get("username"), 
#                 "text": text, 
#                 "label": label_display, 
#                 "score": score,
#                 "polarity": polarity,
#                 "permalink": reply.get("permalink"),
#                 "timestamp": reply.get("timestamp")
#             })
            
#         except Exception as e:
#             print(f"❌ Exception during analysis: {e}")
#             per_reply.append({"id": reply.get("id"), "text": text, "error": str(e)})

#     if not sentiments_vals:
#         return {
#             "per_reply": per_reply, 
#             "cumulative_sentiment": 0.0, 
#             "overall_sentiment": "No Sentiment Data", 
#             "recommendations": ["No replies with valid text found to analyze."]
#         }

#     cumulative = sum(sentiments_vals) / len(sentiments_vals)

#     # Adjusted thresholds for the 3-class model
#     if cumulative > 0.1: 
#         overall = "Overall Positive"
#         recommendations = ["Audience sentiment is positive! Keep creating content like this."]
#     elif cumulative < -0.1: 
#         overall = "Overall Negative"
#         recommendations = ["Sentiment is negative. Review comments for constructive feedback."]
#     else: 
#         overall = "Overall Neutral"
#         recommendations = ["Sentiment is neutral/balanced. Try asking questions to spark debate."]
    
#     return {
#         "per_reply": per_reply,
#         "cumulative_sentiment": cumulative,
#         "overall_sentiment": overall,
#         "recommendations": recommendations
#     }

def analyze_replies_sentiment(replies_list):
    """
    Runs sentiment analysis LOCALLY using VADER.
    This eliminates API timeouts (410/503 errors) completely.
    """
    if not replies_list:
        return {
            "per_reply": [],
            "cumulative_sentiment": 0.0,
            "overall_sentiment": "No Text Replies",
            "recommendations": ["No replies with text found to analyze."]
        }

    # Initialize VADER analyzer (Runs locally, no API key needed)
    analyzer = SentimentIntensityAnalyzer()
    
    per_reply = []
    sentiments_vals = []

    print(f"🔍 DEBUG: Analyzing {len(replies_list)} replies locally with VADER...")

    for reply in replies_list:
        text = reply.get("text", "")
        if not text.strip(): continue

        try:
            # VADER gives a 'compound' score from -1.0 (negative) to 1.0 (positive)
            scores = analyzer.polarity_scores(text)
            compound_score = scores['compound']
            
            # Determine Label based on VADER standards
            if compound_score >= 0.05:
                label = "POSITIVE"
            elif compound_score <= -0.05:
                label = "NEGATIVE"
            else:
                label = "NEUTRAL"

            sentiments_vals.append(compound_score)

            per_reply.append({
                "username": reply.get("username"), 
                "text": text, 
                "label": label, 
                "score": float(compound_score),
                "polarity": float(compound_score),
                "permalink": reply.get("permalink"),
                "timestamp": reply.get("timestamp")
            })
            
        except Exception as e:
            print(f"❌ Error: {e}") #print(f"❌ VADER Error: {e}")
            per_reply.append({"text": text, "error": str(e)})

    if not sentiments_vals:
        return {
            "per_reply": per_reply,
            "cumulative_sentiment": 0.0,
            "overall_sentiment": "No Sentiment Data", 
            "recommendations": ["Could not analyze sentiment."]
        }

    cumulative = sum(sentiments_vals) / len(sentiments_vals)

    # Generate Recommendations based on score
    if cumulative > 0.05:
        overall = "Overall Positive"
        recommendations = [
            "Audience sentiment is positive! Keep creating content like this.",
            "Engage with the top positive comments to build community."
        ]
    elif cumulative < -0.05:
        overall = "Overall Negative"
        recommendations = [
            "Sentiment is trending negative. Review comments for constructive feedback.",
            "Consider posting a clarification or follow-up if there is confusion."
        ]
    else:
        overall = "Overall Neutral"
        recommendations = [
            "Sentiment is balanced. Try asking a specific question to spark more debate.",
            "Use the Keyword Recommendations tool to find more engaging topics."
        ]
    
    return {
        "per_reply": per_reply,
        "cumulative_sentiment": cumulative,
        "overall_sentiment": overall,
        "recommendations": recommendations
    }

def generate_positive_tips(replies_text):
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        return client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': "You are a social media strategist."},
                {'role': 'user', 'content': f"Analyze positive feedback: {replies_text}"}
            ],
            model="llama-3.3-70b-versatile"
        ).choices[0].message.content
    except Exception as e:
        return f"Error: {e}"