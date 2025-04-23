import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# 1. Credentials from env
NEY_API_KEY        = os.environ["NEY_API_KEY"]
AIRTABLE_TOKEN     = os.environ["AIRTABLE_ACCESS_TOKEN"]
AIRTABLE_BASE_ID   = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE     = os.environ["AIRTABLE_TABLE_NAME"]

# 2. Helper to push records to Airtable
def push_to_airtable(records):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "records": [
            {"fields": {
                "Username":  r["username"],
                "Text":      r["text"],
                "Media":     [{"url": m} for m in r["media"]],
                "Link":      r["link"],
                "Farcaster Likes": r["farcaster_likes"],
                "Farcaster Timestamp": r["timestamp"]
            }}
            for r in records
        ]
    }

    resp = requests.post(url, json=payload, headers=headers)
    try:
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError:
        # Instead of crashing, return Airtable’s error details
        return {
            "error":  resp.status_code,
            "detail": resp.json()
        }


# 3. Main route: scrape, filter, and sync
@app.route("/", methods=["GET"])
def scrape_and_sync():
    # --- Scrape from Neynar ---
    channel = request.args.get("channel", "nouns-draws")
    # ← NEW: pagination cursor (omit on first run)
    cursor     = request.args.get("cursor", None)
    url     = "https://api.neynar.com/v2/farcaster/feed/channels"
    headers = {
        "accept": "application/json",
        "api_key": NEY_API_KEY
    }
    params = {
        "channel_ids":  channel,
        "with_recasts": False,
        "with_replies": False,
        "limit":        20,
        **({"cursor": cursor} if cursor else {})
    }
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    raw_casts = data.get("casts", [])
    # ← NEW: give back the cursor for the next page
    next_cursor = data.get("next", {}).get("cursor")

    # --- Filter for image embeds ---
    filtered = []
    for item in raw_casts:
        embeds = item.get("embeds", [])
        image_urls = [
            e["url"]
            for e in embeds
            if e.get("url") and 
               "image" in e.get("metadata", {}).get("content_type", "")
        ]
        if not image_urls:
            continue

        author = item.get("author", {}).get("username", "")
        farcaster_likes = item.get("reactions", {}).get("likes_count", 0)
        filtered.append({
            "username": author,
            "text":     item.get("text", ""),
            "media":    image_urls,
            "timestamp":item.get("timestamp"),
            "link":     f"https://warpcast.com/{author}/{item.get('hash')}",
            "farcaster_likes": farcaster_likes
        })

    # --- Sync to Airtable ---
    airtable_resp = push_to_airtable(filtered)

    # --- Return both for confirmation ---
    return jsonify({
        "airtable_sync": airtable_resp,
        "casts":         filtered,
        "next_cursor": next_cursor
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
