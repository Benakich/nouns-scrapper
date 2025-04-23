import os
import requests
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

API_KEY = os.environ.get("NEY_API_KEY")

@app.route("/", methods=["GET"])
def scrape_nouns_channel():
    # 1. Grab params
    channel = request.args.get("channel", "nouns-draws")
    debug   = request.args.get("debug", "false").lower() in ("1", "true")

    # 2. Fetch from Neynar
    url = "https://api.neynar.com/v2/farcaster/feed/channel"
    headers = {"accept": "application/json", "api_key": API_KEY}
    params = {"channel": channel, "limit": 20}
    resp = requests.get(url, headers=headers, params=params)
    
    data = resp.json()
    raw_casts = data.get("casts", [])
    logging.info(f"Fetched {len(raw_casts)} raw casts for channel '{channel}'")

    # 3. If debug, return first 5 casts unfiltered
    if debug:
        return jsonify({"raw_casts": raw_casts[:5]})

    # 4. Otherwise filter for images as before
    filtered = []
    for item in raw_casts:
        embeds = item.get("embeds", [])
        image_urls = [
            e.get("url")
            for e in embeds
            if e.get("url") and "image" in e.get("mime_type", "")
        ]
        if not image_urls:
            continue

        author = item.get("author", {}).get("username", "")
        filtered.append({
            "username": author,
            "text": item.get("text", ""),
            "media": image_urls,
            "timestamp": item.get("timestamp"),
            "link": f"https://warpcast.com/{author}/{item.get('hash')}"
        })

    return jsonify({"casts": filtered})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
