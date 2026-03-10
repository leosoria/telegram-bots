from telethon import TelegramClient, events
import requests
import re
from urllib.parse import quote
from deep_translator import GoogleTranslator

# TELEGRAM
api_id = 17877920
api_hash = "4a5893a520b6d4adc40cfa0015b3ecae"

# OMDB (rating IMDB + parental guide + sinopsis)
OMDB_KEY = "f296cc45"

# TMDB (info principal: géneros, duración, reparto, poster)
TMDB_KEY = "8f542c554a666240a9247a820c39dbbe"
TMDB_BASE = "https://api.themoviedb.org/3"

TARGET_CHAT = "My Movies Index"

client = TelegramClient("session", api_id, api_hash)


async def in_target_chat(event):
    chat = await event.get_chat()
    return getattr(chat, "title", "") == TARGET_CHAT


# ----------------------------
# EXTRAER TEXTO LIMPIO DE MARKDOWN
# Convierte [Sergio (2020)](https://t.me/...) → Sergio (2020)
# ----------------------------

def clean_markdown_links(text):
    return re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)


# ----------------------------
# EXTRAER SOLO TITULO Y AÑO DE LA PRIMERA LINEA
# Maneja casos como:
#   "Sergio (2020)"
#   "Sergio (2020) | 118 min | Drama"
#   "Sergio (2020) PG-R | 118 min | Drama [6.2]"
# ----------------------------

def extract_title_from_line(line):
    # Quitar markdown primero
    line = clean_markdown_links(line)
    # Tomar solo lo que está antes del primer "|" o "[" o "PG-"
    line = re.split(r'\||\[|PG-', line)[0].strip()
    return line


# ----------------------------
# SEPARAR TITULO Y LINKS
# ----------------------------

def split_message(text):

    lines = text.split("\n")
    raw_title = lines[0].strip()

    # Titulo limpio para buscar (sin markdown, sin info extra)
    clean_title = extract_title_from_line(raw_title)

    links = []
    other = []

    for line in lines[1:]:
        line = line.strip()
        if "http" in line or "t.me" in line:
            links.append(line)
        elif line:
            other.append(line)

    # Conservar URLs embebidas en el título
    urls_in_title = re.findall(r'\((https?://[^\)]+)\)', raw_title)
    for url in urls_in_title:
        if url not in links:
            links.insert(0, url)

    return clean_title, links, other


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
# OBTENER INFO OMDB
# ----------------------------

def get_omdb(title, year=None):

    try:
        query_encoded = quote(title)
        if year:
            url = f"http://www.omdbapi.com/?t={query_encoded}&y={year}&apikey={OMDB_KEY}"
        else:
            url = f"http://www.omdbapi.com/?t={query_encoded}&apikey={OMDB_KEY}"

        r = requests.get(url, timeout=5).json()

        if r.get("Response") == "True":
            return r
    except:
        pass

    return None


# ----------------------------
# OBTENER INFO TMDB
# ----------------------------

def get_movie(query):

    print("----- DEBUG -----")
    print("QUERY ORIGINAL:", query)

    title, year = parse_title_year(query)

    print("TITULO FINAL:", title)
    print("AÑO DETECTADO:", year)

    # --- TMDB: géneros, duración, reparto, poster ---
    search_url = f"{TMDB_BASE}/search/movie"
    params = {
        "api_key": TMDB_KEY,
        "query": title,
        "language": "es-ES",
    }
    if year:
        params["year"] = year

    search_r = requests.get(search_url, params=params, timeout=5).json()
    results = search_r.get("results", [])

    print("RESULTADOS TMDB:", len(results))

    if not results:
        print("No se encontraron resultados en TMDB")
        print("-----------------")
        return None

    movie_id = results[0]["id"]

    detail_url = f"{TMDB_BASE}/movie/{movie_id}"
    detail_params = {
        "api_key": TMDB_KEY,
        "language": "es-ES",
        "append_to_response": "credits"
    }
    detail = requests.get(detail_url, params=detail_params, timeout=5).json()

    tmdb_title = detail.get("title", title)
    release_year = (detail.get("release_date") or "")[:4]
    runtime = detail.get("runtime")
    runtime_str = f"{runtime} min" if runtime else "N/A"

    genres = [g["name"] for g in detail.get("genres", [])]
    genre_str = ", ".join(genres) if genres else "N/A"

    cast_list = detail.get("credits", {}).get("cast", [])[:5]
    cast_str = ", ".join([c["name"] for c in cast_list]) if cast_list else "N/A"

    poster_path = detail.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    print("PELICULA ENCONTRADA:", tmdb_title)

    # --- OMDB: parental guide + IMDB rating + sinopsis ---
    omdb = get_omdb(tmdb_title, release_year)

    if omdb:
        rated = omdb.get("Rated", "")
        pg = f"PG-{rated}" if rated and rated != "N/A" else "PG-NR"
        imdb_rating = omdb.get("imdbRating", "N/A")
        plot_raw = omdb.get("Plot", "")
        try:
            plot_es = GoogleTranslator(source="auto", target="es").translate(plot_raw)
        except:
            plot_es = plot_raw
    else:
        pg = "PG-NR"
        imdb_rating = "N/A"
        plot_es = detail.get("overview") or "Sin sinopsis disponible."

    # Quitar punto final de la sinopsis
    plot_es = plot_es.rstrip(".")

    print("-----------------")

    text = (
        f"{tmdb_title} ({release_year})\n"
        f"{pg} | {runtime_str} | {genre_str} [{imdb_rating}]\n"
        f"Synopsis: {plot_es}\n"
        f"Cast: {cast_str}"
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
