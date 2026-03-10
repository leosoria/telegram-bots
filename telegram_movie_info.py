from telethon import TelegramClient, events
import requests
import re
from urllib.parse import quote

# TELEGRAM
api_id = 17877920
api_hash = "4a5893a520b6d4adc40cfa0015b3ecae"

# OMDB (solo para rating IMDB)
OMDB_KEY = "f296cc45"

# TMDB (info principal)
TMDB_KEY = "8f542c554a666240a9247a820c39dbbe"
TMDB_BASE = "https://api.themoviedb.org/3"

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
# LIMPIAR TITULO Y AÑO
# ----------------------------

def parse_title_year(query):

    query = query.replace(",", "").strip()

    year = None
    match = re.search(r'\((\d{4})\)|(\b\d{4}\b)', query)

    if match:
        year = match.group(1) or match.group(2)
        query = re.sub(r'\s*\(\d{4}\)|\s*\b\d{4}\b', '', query).strip()

    return query, year


# ----------------------------
# OBTENER RATING IMDB (OMDB)
# ----------------------------

def get_imdb_rating(title, year=None):

    try:
        query_encoded = quote(title)
        if year:
            url = f"http://www.omdbapi.com/?t={query_encoded}&y={year}&apikey={OMDB_KEY}"
        else:
            url = f"http://www.omdbapi.com/?t={query_encoded}&apikey={OMDB_KEY}"

        r = requests.get(url, timeout=5).json()

        if r.get("Response") == "True":
            return r.get("imdbRating", "N/A")
    except:
        pass

    return "N/A"


# ----------------------------
# OBTENER INFO TMDB
# ----------------------------

def get_movie(query):

    print("----- TMDB DEBUG -----")
    print("QUERY ORIGINAL:", query)

    title, year = parse_title_year(query)

    print("TITULO FINAL:", title)
    print("AÑO DETECTADO:", year)

    # Buscar en TMDB
    search_url = f"{TMDB_BASE}/search/movie"
    params = {
        "api_key": TMDB_KEY,
        "query": title,
        "language": "es-ES",
    }
    if year:
        params["year"] = year

    search_r = requests.get(search_url, params=params, timeout=5).json()

    print("RESULTADOS TMDB:", len(search_r.get("results", [])))

    results = search_r.get("results", [])
    if not results:
        print("No se encontraron resultados en TMDB")
        print("----------------------")
        return None

    movie = results[0]
    movie_id = movie["id"]

    # Detalle completo de la película (con créditos)
    detail_url = f"{TMDB_BASE}/movie/{movie_id}"
    detail_params = {
        "api_key": TMDB_KEY,
        "language": "es-ES",
        "append_to_response": "credits"
    }

    detail = requests.get(detail_url, params=detail_params, timeout=5).json()

    print("PELICULA ENCONTRADA:", detail.get("title"))
    print("----------------------")

    # Datos principales
    tmdb_title = detail.get("title", title)
    release_year = (detail.get("release_date") or "")[:4]
    runtime = detail.get("runtime")
    runtime_str = f"{runtime} min" if runtime else "N/A"
    plot_es = detail.get("overview") or "Sin sinopsis disponible."

    # Géneros
    genres = [g["name"] for g in detail.get("genres", [])]
    genre_str = ", ".join(genres) if genres else "N/A"

    # Reparto (primeros 5)
    cast_list = detail.get("credits", {}).get("cast", [])[:5]
    cast_str = ", ".join([c["name"] for c in cast_list]) if cast_list else "N/A"

    # Rating TMDB
    tmdb_score = detail.get("vote_average")
    tmdb_rating = f"{tmdb_score:.1f}" if tmdb_score else "N/A"

    # Rating IMDB via OMDB
    imdb_rating = get_imdb_rating(tmdb_title, release_year)

    # Poster
    poster_path = detail.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    text = (
        f"{tmdb_title} ({release_year}) | "
        f"{runtime_str} | {genre_str}\n"
        f"TMDB: {tmdb_rating} | IMDB: {imdb_rating}\n"
        f"Sinopsis: {plot_es}\n"
        f"Reparto: {cast_str}"
    )

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
