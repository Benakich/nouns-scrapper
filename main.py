import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# 1. Credentials from env
NEY_API_KEY        = os.environ["NEY_API_KEY"]
AIRTABLE_TOKEN     = os.environ["AIRTABLE_ACCESS_TOKEN"]
AIRTABLE_BASE_ID   = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE     = os.environ["AIRTABLE_TABLE_NAME"]

# Helper: read the last cursor from your State table
def get_last_cursor(channel):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/State"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}"
    }
    # filter for the record whose Channel field matches our channel
    params = {
        "filterByFormula": f"{{Channel}}='{channel}'"
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    recs = r.json().get("records", [])
    if not recs:
        return None, None
    rec = recs[0]
    return rec["fields"].get("LastCursor"), rec["id"]


# Helper: write the new cursor back into the State record
def set_last_cursor(record_id, cursor):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/State/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {"fields": {"LastCursor": cursor}}
    resp = requests.patch(url, json=payload, headers=headers)
    resp.raise_for_status()


# 2. Helper to push records to Airtable
def push_to_airtable(records):
    """
    Airtable only accepts up to 10 records per request.
    Split into chunks of 10 and POST each in turn.
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type":  "application/json"
    }
    all_responses = []

    for i in range(0, len(records), 10):
        batch = records[i : i + 10]
        payload = {
            "records": [
                {"fields": {
                    "Username":            r["username"],
                    "Text":                r["text"],
                    "Media":               [{"url": m} for m in r["media"]],
                    "Link":                r["link"],
                    "Farcaster Likes":     r["farcaster_likes"],
                    "Farcaster Timestamp": r["timestamp"]
                }}
                for r in batch
            ]
        }

        resp = requests.post(url, json=payload, headers=headers)
        try:
            resp.raise_for_status()
            all_responses.append(resp.json())
        except requests.HTTPError:
            return {
                "error":  resp.status_code,
                "detail": resp.json()
            }

    return {"batches": all_responses}


# 3. Main route: scrape, filter, and sync
@app.route("/", methods=["GET"])
def scrape_and_sync():
    # --- Scrape from Neynar ---
    channel = request.args.get("channel", "nouns-draws")
    # ← NEW: pagination cursor (omit on first run)
    # automatically fetch the last cursor from Airtable State
    cursor, state_rec_id = get_last_cursor(channel)
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
    # save the new cursor, so next run picks up where we left off
    if state_rec_id:
        set_last_cursor(state_rec_id, next_cursor)


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
