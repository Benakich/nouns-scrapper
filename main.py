from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_KEY = "A6514994-2AD5-4CDD-A3EC-38A35B40B83F"

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

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    filtered_casts = []

    for item in data.get("casts", []):
        embeds = item.get("embeds", [])
        image_urls = [
            e.get("url") for e in embeds
            if e.get("url") and "image" in e.get("mime_type", "")
        ]

        if not image_urls:
            continue

        author = item.get("author", {}).get("username", "")
        cast_url = f"https://warpcast.com/{author}/{item.get('hash')}"

        filtered_casts.append({
            "username": author,
            "text": item.get("text", ""),
            "media": image_urls,
            "timestamp": item.get("timestamp"),
            "link": cast_url
        })

    return jsonify({"casts": filtered_casts})
