import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("NEY_API_KEY", "A6514994-2AD5-4CDD-A3EC-38A35B40B83F")

@app.route("/", methods=["GET"])
def scrape_nouns_channel():
    channel = request.args.get("channel", "nouns-draws")
    url = "https://api.neynar.com/v2/farcaster/feed/channel"
    headers = {
        "accept": "application/json",
        "api_key": API_KEY
    }
    params = {
        "channel": channel,
        "limit": 20
    }

    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()

    filtered = []
    for item in data.get("casts", []):
        image_urls = [
            e.get("url") for e in item.get("embeds", [])
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
    # Get port from env (Railway sets PORT), default to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    # Listen on all interfaces
    app.run(host="0.0.0.0", port=port)
