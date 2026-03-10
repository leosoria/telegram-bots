from telethon import TelegramClient, events
import requests
from deep_translator import GoogleTranslator
from urllib.parse import quote

# TELEGRAM
api_id = 17877920
api_hash = "4a5893a520b6d4adc40cfa0015b3ecae"

# OMDB
OMDB_KEY = "f296cc45"

TARGET_CHAT = "My Movies Index"

client = TelegramClient("session", api_id, api_hash)


async def in_target_chat(event):
    chat = await event.get_chat()
    return getattr(chat, "title", "") == TARGET_CHAT


@client.on(events.NewMessage)
async def movie_info(event):

    if not await in_target_chat(event):
        return

    text = event.raw_text.strip()

    if not text:
        return

    parts = text.split()
    year = None

    # detectar año
    if parts[-1].isdigit() and len(parts[-1]) == 4:
        year = parts[-1]
        title = " ".join(parts[:-1])
    else:
        title = text

    title = quote(title)

    if year:
        url = f"http://www.omdbapi.com/?t={title}&y={year}&apikey={OMDB_KEY}"
    else:
        url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_KEY}"

    r = requests.get(url).json()

    if r.get("Response") == "False":
        return

    plot = r.get("Plot", "")

    try:
        plot_es = GoogleTranslator(source="auto", target="es").translate(plot)
    except:
        plot_es = plot

    cast = r.get("Actors", "").split(",")[:5]
    cast = ", ".join(cast)

    genre = r.get("Genre", "")
    genre = genre.replace("Sci-Fi", "Science Fiction")

    rating = r.get("Rated", "")
    if rating == "R":
        rating = "PG-R"

    msg = f"{r.get('Title')} ({r.get('Year')})\n{rating} | {r.get('Runtime')} | {genre} [{r.get('imdbRating')}]\nSynopsis: {plot_es}\nCast: {cast}"

    poster = r.get("Poster")

    # borrar mensaje original
    await event.delete()

    if poster and poster != "N/A":
        await client.send_file(event.chat_id, poster, caption=msg)
    else:
        await client.send_message(event.chat_id, msg)


client.start()
print("Movie index activo...")
client.run_until_disconnected()
