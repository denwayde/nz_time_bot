# nz_time_bot

Telegram bot that reminds Muslims to perform their daily prayers (prayer times come from the [aladhan.com](https://aladhan.com/prayer-times-api) API, method 14).

## Features

- Initial setup: country, city, madhhab (Hanafi / Shafi'i), reminder time:
  - at the moment the prayer time starts;
  - 30 minutes before the prayer time ends;
  - 1 hour before the prayer time ends.
- A reminder at the right time with a hadith (or without one - configurable via the `/set_hadis_to_time` and `/del_hadis_from_time` commands).
- The "Today's prayer times" button - all five prayer times for the current day.
- `/change_settings` - change country/city/madhhab/reminder time.
- `/delete_user` - delete your data from the bot's database.
- `/send_message_to_admin` - write to the administrator.
- For the administrator: `/users` - list of users, `/send_all` - mailing to all users.

## Installation

1. Clone the repository and install the dependencies (Python 3.8-3.11 is required):

```bash
pip install -r requirements.txt
```

2. Create a `.env` file next to `bot.py`:

```
BOT_TOKEN=your_bot_token_from_BotFather
ADMIN_ID=your_telegram_id   # optional, defaults to the ID of the first admin
```

3. Start the bot:

```bash
python bot.py
```

The SQLite database (`nzt.db`) is created automatically on the first start - the tables are initialized by the bot itself, no manual setup is needed.

## Importing hadiths

Hadiths are stored in the `khadisy` table of the SQLite database (`nzt.db`). Recommended import source: a plain-text file `khadisy.txt` (one hadith per paragraph, paragraphs separated by a blank line). A starter collection is provided in `khadisy_en.txt` - rename or copy it to `khadisy.txt`:

```bash
python main.py
```

Re-running the script does not create duplicates. The legacy Russian book `khadisy.epub` is also supported as an import source.

## Structure

| File | Purpose |
| --- | --- |
| `bot.py` | bot logic, FSM setup flow, reminder scheduler (English UI) |
| `db.py` | SQLite work (`nzt.db`), automatic table initialization, rows are read by column names |
| `config_reader.py` | config from `.env` (bot token, admin ID) |
| `main.py` | one-off hadith import from `khadisy.txt` (recommended) or `khadisy.epub` |
| `khadisy_en.txt` | starter English hadith collection for the import |
| `*_test.py`, `data_test.json` | draft test/debug files |
