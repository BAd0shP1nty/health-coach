# AI Health Coach for Indian Diets - chat agent

A DeepSeek-powered coaching agent you talk to on your phone (Telegram). Send a **voice note** or just
**type** what you ate; ask for meal ideas; get daily check-ins. No app install, no APK.

## How it works
- `hc/agent.py` - the agent: DeepSeek (function calling, `hc/llm.py`) + 11 tools (profile, food search, logging, summary, notes, recommendations).
  DeepSeek does the reasoning and conversation; every number comes from code (`hc/calc.py`, `data/foods.csv`, SQLite).
- Voice notes are transcribed on the server (`hc/stt.py`, faster-whisper). Photo input is switched off for now; the code (`hc/vision.py`, `agent.respond(images=...)`) is kept for later.
- Memory: per-customer SQLite + ChromaDB vector store (`hc/rag.py`) in `data/users/<id>/` - fully separate per customer.
- Safety in code, not just prompts: calorie floors and warnings (`hc/calc.py`), diet/allergy filtering of suggested foods,
  the medical disclaimer is prepended in code to every reply that follows a recommendation, daily message cap per user.
- `hc/channels/telegram_bot.py` - Telegram front end. Other channels (WhatsApp, a future Android app) can reuse `agent.respond()`.
- `app.py` (optional) - the older Streamlit desktop UI on the same data/logic. Not needed for the bot.

## Web chat (public demo)
`web_chat.py` is a Streamlit chat page using the same agent; it shows the retrieved RAG memory under each answer. Deploy it as a free public URL on Streamlit Community Cloud - see DEPLOY_GUIDE.txt (`Dockerfile` is there for other container hosts). Run locally: `streamlit run web_chat.py`.

## Run it (Telegram bot)
See SETUP_GUIDE.txt (step by step). Short version:
```
pip install -r requirements.txt
copy .env.example .env      # add DEEPSEEK_API_KEY and TELEGRAM_BOT_TOKEN
python -m hc.channels.telegram_bot
```
Test without Telegram: `python -m hc.chat`.  Tests: `python -m pytest -q`.

## Data and accuracy
`data/foods.csv` has 158 approximate per-100 g values (IFCT 2017 / USDA typical, rounded) - not a certified database; everything
is labelled an estimate. Packaged-food lookup (`hc/packaged.py`, Open Food Facts) is available to the
desktop app; wiring it into the chat agent is a possible next step.

## Privacy
Messages and relevant data are sent to the DeepSeek API (a China-based provider - read its privacy policy) to generate replies. `/delete_my_data` erases a customer's
folder. See `/privacy` in the bot.

*Educational use only. Not medical advice - consult your doctor.*
