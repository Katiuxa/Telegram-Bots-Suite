# OnlyNews

Telegram bot: paste a news URL and it returns the text (and the article photos). It runs as `mi_bot.service`.

## The problem and what was done

- **A real paywall:** if the publisher does not put the body in the HTML, there is no article. The paywall is not bypassed.
- **Many sites do ship the text in the page** (`<p>`, JSON-LD, domain selectors). That is what it extracts.
- At first only `<p>` paragraphs came out. `article_extract.py` was extended to **include the article photos** (`fetch_image_bytes`, then send them to Telegram).

National Geographic and other domains have their own selectors. Everything else goes through a universal list, plus trafilatura if it is installed.

## Stack

Python · BeautifulSoup · requests · trafilatura (optional) · pyTelegramBotAPI

## Run

```bash
cd only-noticias
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
python3 mi_bot.py
```

## What it shows

Telling "the HTML already contains the text" apart from "a real paywall", and extending the parser (images) without inventing content.
