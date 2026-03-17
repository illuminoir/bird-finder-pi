from telegram.ext import ApplicationBuilder, CommandHandler
from db import init_db, get_last_detection
from zoneinfo import ZoneInfo
from datetime import datetime
from dotenv import load_dotenv
import os

async def birds(update, context):
    result = get_last_detection()

    if not result:
        update.message.reply_text("No birds detected yet 🥲")
        return

    species, confidence, timestamp_utc = result

    dt_utc = datetime.fromisoformat(timestamp_utc)
    dt_uk = dt_utc.astimezone(ZoneInfo("Europe/London"))

    message = (
        f"🐦 Last bird detected:\n"
        f"{species}\n"
        f"{dt_uk.strftime('%d %b %Y at %H:%M')} (UK time)\n"
        f"Confidence: {round(confidence*100, 1)}%"
    )

    await update.message.reply_text(message)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("birds", birds))

    app.run_polling()


if __name__ == "__main__":
    main()