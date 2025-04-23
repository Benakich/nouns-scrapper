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
                    "Cast Hash":           r["hash"], 
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
    # 1. Fetch all channels and their cursors from the State table
    url_state = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/State"
    headers_state = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    resp_state = requests.get(url_state, headers=headers_state)
    resp_state.raise_for_status()
    states = resp_state.json().get("records", [])

    summary = []

    for rec in states:
        channel       = rec["fields"]["Channel"]
        cursor        = rec["fields"].get("LastCursor")
        state_rec_id  = rec["id"]

        # 2. Fetch the next page of casts for this channel
        neynar_url = "https://api.neynar.com/v2/farcaster/feed/channels"
        headers_neynar = {
            "accept":   "application/json",
            "api_key":  NEY_API_KEY
        }
        params = {
            "channel_ids":  channel,
            "with_recasts": False,
            "with_replies": False,
            "limit":        20,
            **({"cursor": cursor} if cursor else {})
        }
        r = requests.get(neynar_url, headers=headers_neynar, params=params)
        r.raise_for_status()
        data = r.json()
        raw_casts  = data.get("casts", [])
        next_cursor= data.get("next", {}).get("cursor")

        # 3. Filter for image embeds and collect fields
        filtered = []
        for item in raw_casts:
            embeds = item.get("embeds", [])
            image_urls = [
                e["url"]
                for e in embeds
                if e.get("url") and "image" in e.get("metadata", {}).get("content_type", "")
            ]
            if not image_urls:
                continue

            author = item.get("author", {}).get("username", "")
            farcaster_likes = item.get("reactions", {}).get("likes_count", 0)
            filtered.append({
                "username":            author,
                "text":                item.get("text", ""),
                "media":               image_urls,
                "link":                f"https://warpcast.com/{author}/{item.get('hash')}",
                "Farcaster Likes":     farcaster_likes,
                "Farcaster Timestamp": item.get("timestamp"),
                "hash":                item.get("hash"),
                "Channel":             channel
            })

        # Deduplicate by pulling existing Cast Hashes for this channel
        airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
        headers_at   = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
        params       = {
            "filterByFormula": f"{{Channel}}='{channel}'",
            "fields":          ["Cast Hash"],
            "pageSize":        100
        }
        resp_existing = requests.get(airtable_url, headers=headers_at, params=params)

        if not resp_existing.ok:
        # Return Airtable’s error details right in the response
            return jsonify({
                "error":           "Failed to fetch existing hashes",
                "status_code":     resp_existing.status_code,
                "airtable_detail": resp_existing.json()
        }), resp_existing.status_code

        recs = resp_existing.json().get("records", [])
        existing_hashes = {rec["fields"].get("Cast Hash") for rec in recs if rec["fields"].get("Cast Hash")}
        
        resp_existing.raise_for_status()
        existing_hashes = {
        rec["fields"].get("Cast Hash")
        for rec in resp_existing.json().get("records", [])
        if rec["fields"].get("Cast Hash") is not None
        }

        # Keep only those not already in Airtable
        unique_records = [
        r for r in filtered
        if r["hash"] not in existing_hashes
        ]

        # Push only the new ones
        push_resp = push_to_airtable(unique_records)

        
        # 4. Push these records to the Casts table in Airtable
        #push_resp = push_to_airtable(filtered)

        # 5. Update the State table with the new cursor
        patch_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/State/{state_rec_id}"
        patch_headers = {
            "Authorization": f"Bearer {AIRTABLE_TOKEN}",
            "Content-Type":  "application/json"
        }
        patch_body = {"fields": {"LastCursor": next_cursor}}
        patch_resp = requests.patch(patch_url, json=patch_body, headers=patch_headers)
        patch_resp.raise_for_status()

        summary.append({
            "channel":      channel,
            "fetched":      len(filtered),
            "next_cursor":  next_cursor,
            "push_result":  push_resp
        })

    return jsonify(summary)



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
