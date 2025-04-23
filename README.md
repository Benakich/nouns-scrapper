# Farcaster → Airtable Scraper

A self-hosted service that automatically pulls the latest image-casts from one or more Farcaster channels, deduplicates by cast-hash, and syncs them into an Airtable base on a regular schedule.

Done using low-code and automation

##  Features

- **Multi-channel support**: track as many channels as you like by adding rows to the State table.  
- **Hourly (or custom interval) polling**: fetches the latest **20** image-casts per channel each run.  
- **Deduplication**: skips any cast whose hash already exists in your Airtable.  
- **Airtable integration**: writes Username, Text, Media, Link, Cast Hash, Likes, Timestamp, and Channel.  

---

## 📋 Prerequisites

- **Python 3.12**  
- A **Railway**, **Heroku**, or any server capable of running a Flask app + cron jobs  
- An **Airtable** account with a base (see next section)  
- A Farcaster/Neynar API key  

---

## 🛠Airtable Setup

1. **Create a new base** (or copy https://airtable.com/appXZMKGACF1jzRH0/shrfui31mNWcf5Yxw ).  
2. Add two tables:

   ### **State**  
   | Field       | Type              | Notes                                     |
   | ----------- | ----------------- | ----------------------------------------- |
   | Channel     | Single line text  | Farcaster channel ID (e.g. `nouns-draws`) |
   | LastCursor  | Single line text  | (leave blank initially)                   |

   Create one record per channel you want to scrape.

   ### **Casts**  
   | Field                | Type               | Notes                                    |
   | -------------------- | ------------------ | ---------------------------------------- |
   | Username             | Single line text   | cast author username                     |
   | Text                 | Long text          | cast text                                |
   | Media                | Attachment         | one or more image URLs                   |
   | Link                 | URL                | warpcast.com link                        |
   | Cast Hash            | Single line text   | unique cast hash                         |
   | Farcaster Likes      | Number             | number of likes on Farcaster             |
   | Farcaster Timestamp  | Date / time        | cast timestamp                           |
   | Channel              | Single line text   | channel ID                               |

---

##  Installation

```bash
# 1. Clone repo
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# 2. Install dependencies
pip install -r requirements.txt
