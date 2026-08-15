# Nazerva - AI-Assisted E-commerce Recommendation Bot

> Bachelor's-thesis prototype (2026) of a Ukrainian-language Telegram assistant for product discovery and personalised recommendations over a seeded clothing catalogue.

This is an academic portfolio project, not a production e-commerce system. It demonstrates a complete conversational shopping flow: local intent parsing, product filtering, personalised ranking, Gemini-assisted replies, and manual order capture.

## Highlights

- Telegram interface for catalogue browsing, search, filters, favourites, cart, orders, and role-gated admin actions
- Ukrainian-language intent parser for category, price, size, and colour
- SQLite persistence for the catalogue, preferences, interactions, sessions, and order workflow
- Content-based recommendations using engineered product features and cosine similarity
- Gemini 2.5 Flash receives ranked candidate-product context and returns a parsed JSON reply
- Graceful local fallback when Gemini is unavailable
- Automated unit tests and a GitHub Actions workflow

## Architecture

Telegram user -> bot and handlers -> local intent parser -> SQLite candidate filtering -> content-based ranker -> Gemini response

The ranker combines three signals:

- explicit onboarding preferences;
- parsed search-query history;
- implicit events: views, likes, and cart additions.

Each product is represented by category, brand, material, colour, and normalised price features. Candidate products are ranked with cosine similarity. Gemini is prompted only with the ranked candidate context, and returned product IDs are filtered against that candidate set before use.

## Tech stack

Python 3.12 | python-telegram-bot | Google Gemini API | SQLite | NumPy | scikit-learn | pytest

## Run locally

1. Clone the repository and enter its directory.
2. Create and activate a virtual environment.

       python -m venv .venv
       # Windows PowerShell
       .venv\Scripts\Activate.ps1
       # macOS/Linux
       source .venv/bin/activate

3. Install dependencies and create local configuration.

       python -m pip install -r requirements.txt
       # Windows PowerShell
       Copy-Item .env.example .env
       # macOS/Linux
       cp .env.example .env

4. Add a Telegram bot token to <code>.env</code>. A Gemini key is optional for local testing, but required for Gemini-generated replies.
5. Create the seeded demo catalogue and start the bot.

       python seed_data.py
       python bot.py

## Tests

Run the automated unit tests without a Telegram or Gemini API key:

    python -m pytest

The tests cover intent parsing, product vectorisation, cosine-similarity behaviour, and validation of model-provided product IDs. They do not cover the Telegram transport, live Gemini calls, or a deployed payment flow.

## Scope and limitations

- The catalogue is seeded demo data; images are placeholders.
- The interface and parser are Ukrainian-language, and prices are in UAH.
- Orders use a manual payment and fulfilment flow. There is no payment gateway or live inventory integration.
- No user data or SQLite database is committed to the repository.
- This prototype has no deployment or production security layer.

## Academic context

Bachelor's thesis project, 2026.
