from telethon import TelegramClient, events
import requests
import re
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


# ----------------------------
# SEPARAR TITULO Y LINKS
# ----------------------------

def split_message(text):

    lines = text.split("\n")

    title = lines[0].strip()

    links = []
    other = []

    for line in lines[1:]:

        line = line.strip()

        if "http" in line or "t.me" in line:
            links.append(line)
        elif line:
            other.append(line)

    return title, links, other


# ----------------------------
# OBTENER INFO OMDB
# ----------------------------

def get_movie(query):

    print("----- OMDB DEBUG -----")
    print("QUERY ORIGINAL:", query)

    query = query.replace(",", "").strip()
    print("QUERY LIMPIA:", query)

    # Detectar año con o sin paréntesis: (2014) o 2014
    year = None
    match = re.search(r'\((\d{4})\)|(\b\d{4}\b)', query)

    if match:
        year = match.group(1) or match.group(2)
        query = re.sub(r'\s*\(\d{4}\)|\s*\b\d{4}\b', '', query).strip()

    print("TITULO FINAL:", query)
    print("AÑO DETECTADO:", year)

    query_encoded = quote(query)

    if year:
        url = f"http://www.omdbapi.com/?t={query_encoded}&y={year}&apikey={OMDB_KEY}"
    else:
        url = f"http://www.omdbapi.com/?t={query_encoded}&apikey={OMDB_KEY}"

    print("URL OMDB:", url)

    r = requests.get(url).json()

    print("RESPUESTA OMDB:", r)
    print("----------------------")

    if r.get("Response") == "False":
        return None

    plot = r.get("Plot", "")

    try:
        plot_es = GoogleTranslator(source="auto", target="es").translate(plot)
    except:
        plot_es = plot

    genre = r.get("Genre", "")
    genre = genre.replace("Sci-Fi", "Science Fiction")

    rating = r.get("Rated", "")
    if rating:
        rating = f"PG-{rating}"

    cast = r.get("Actors", "").split(",")[:5]
    cast = ", ".join(cast)

    text = (
        f"{r.get('Title')} ({r.get('Year')}) "
        f"{rating} | {r.get('Runtime')} | {genre} "
        f"[{r.get('imdbRating')}]\n"
        f"Synopsis: {plot_es}\n"
        f"Cast: {cast}"
    )

    poster = r.get("Poster")

    return {
        "text": text,
        "poster": poster
    }


# ----------------------------
# /INFO (SOLO TEXTO)
# ----------------------------

@client.on(events.NewMessage(pattern="^/info"))
async def info(event):

    if not await in_target_chat(event):
        return

    if not event.reply_to_msg_id:
        return

    msg = await event.get_reply_message()

    if not msg.text:
        return

    title, links, other = split_message(msg.text)

    data = get_movie(title)

    if not data:
        await event.reply("Película no encontrada")
        return

    new_text = data["text"]

    if other:
        new_text += "\n" + "\n".join(other)

    if links:
        new_text += "\n\n" + "\n".join(links)

    await client.edit_message(
        event.chat_id,
        msg.id,
        new_text
    )

    await event.delete()


# ----------------------------
# /INFOP (TEXTO + POSTER)
# ----------------------------

@client.on(events.NewMessage(pattern="^/infop"))
async def infop(event):

    if not await in_target_chat(event):
        return

    if not event.reply_to_msg_id:
        return

    msg = await event.get_reply_message()

    if not msg.text:
        return

    title, links, other = split_message(msg.text)

    data = get_movie(title)

    if not data:
        await event.reply("Película no encontrada")
        return

    new_text = data["text"]

    if other:
        new_text += "\n" + "\n".join(other)

    if links:
        new_text += "\n\n" + "\n".join(links)

    await client.edit_message(
        event.chat_id,
        msg.id,
        new_text,
        file=data["poster"]
    )

    await event.delete()


client.start()
print("Bot activo...")
client.run_until_disconnected()
