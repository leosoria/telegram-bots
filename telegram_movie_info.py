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
# NORMALIZAR PARENTAL GUIDE
# PG-R → PG-R
# PG-PG → PG
# PG-Not Rated / PG-NR → PG-NR
# PG-G → G
# ----------------------------

def format_pg(rated):
    if not rated or rated in ("N/A", "Not Rated", "NR", "Unrated"):
        return "PG-NR"
    # Casos que ya incluyen "PG" en el nombre: PG, PG-13
    if rated.startswith("PG"):
        return rated
    # G no lleva prefijo
    if rated == "G":
        return "G"
    # R, NC-17, TV-MA, etc. → PG-R, PG-NC-17, etc.
    return f"PG-{rated}"


# ----------------------------
# ACORTAR SINOPSIS
# Corta en el primer punto después de 300 caracteres,
# o en el punto más cercano a 400 si no hay uno antes
# ----------------------------

def shorten_synopsis(text, max_chars=300):
    if len(text) <= max_chars:
        return text
    # Buscar el primer punto después de max_chars
    cut = text.find(".", max_chars)
    if cut == -1 or cut > max_chars + 150:
        # No hay punto cercano, cortar en la última palabra antes del límite
        cut = text.rfind(" ", 0, max_chars)
    return text[:cut].rstrip(".")


# ----------------------------
# EXTRAER TEXTO LIMPIO DE MARKDOWN
# ----------------------------

def clean_markdown_links(text):
    return re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)


# ----------------------------
# EXTRAER SOLO TITULO Y AÑO DE LA PRIMERA LINEA
# ----------------------------

def extract_title_from_line(line):
    line = clean_markdown_links(line)
    line = re.split(r'\||\[|PG-', line)[0].strip()
    return line


# ----------------------------
# SEPARAR TITULO Y LINKS
# ----------------------------

def split_message(text):

    lines = text.split("\n")
    raw_title = lines[0].strip()
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

    # --- Buscar en TMDB en inglés ---
    search_url = f"{TMDB_BASE}/search/movie"
    params = {
        "api_key": TMDB_KEY,
        "query": title,
        "language": "en-US",
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

    # --- Detalle en inglés: título, géneros, duración, reparto ---
    detail_en = requests.get(detail_url, params={
        "api_key": TMDB_KEY,
        "language": "en-US",
        "append_to_response": "credits"
    }, timeout=5).json()

    # --- Detalle en español: solo sinopsis ---
    detail_es = requests.get(detail_url, params={
        "api_key": TMDB_KEY,
        "language": "es-ES",
    }, timeout=5).json()

    # Título original en inglés
    tmdb_title = detail_en.get("original_title") or detail_en.get("title", title)
    release_year = (detail_en.get("release_date") or "")[:4]
    runtime = detail_en.get("runtime")
    runtime_str = f"{runtime} min" if runtime else "N/A"

    # Géneros en inglés
    genres = [g["name"] for g in detail_en.get("genres", [])]
    genre_str = ", ".join(genres) if genres else "N/A"

    # Reparto
    cast_list = detail_en.get("credits", {}).get("cast", [])[:5]
    cast_str = ", ".join([c["name"] for c in cast_list]) if cast_list else "N/A"

    # Poster
    poster_path = detail_en.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    print("PELICULA ENCONTRADA:", tmdb_title)

    # --- Sinopsis en español ---
    plot_es = detail_es.get("overview", "").strip()

    if not plot_es:
        omdb_for_plot = get_omdb(tmdb_title, release_year)
        if omdb_for_plot:
            plot_raw = omdb_for_plot.get("Plot", "")
            try:
                plot_es = GoogleTranslator(source="auto", target="es").translate(plot_raw)
            except:
                plot_es = plot_raw

    if not plot_es:
        plot_es = "Sin sinopsis disponible"

    # Acortar y limpiar sinopsis
    plot_es = shorten_synopsis(plot_es)
    plot_es = plot_es.rstrip(".")

    # --- OMDB: parental guide + IMDB rating ---
    omdb = get_omdb(tmdb_title, release_year)

    if omdb:
        rated = omdb.get("Rated", "")
        pg = format_pg(rated)
        imdb_rating = omdb.get("imdbRating", "")
        imdb_rating = imdb_rating if imdb_rating and imdb_rating != "N/A" else "0.0"
    else:
        pg = "PG-NR"
        imdb_rating = "0.0"

    print("-----------------")

    text = (
        f"{tmdb_title} ({release_year})\n"
        f"{pg} | {runtime_str} | {genre_str} **[{imdb_rating}]**\n"
        f"> **Synopsis:** {plot_es}\n"
        f"Cast: {cast_str}"
    )

    return {
        "text": text,
        "poster": poster
    }


# ----------------------------
# HANDLER COMPARTIDO
# ----------------------------

async def handle(event, with_poster=False):

    if not await in_target_chat(event):
        return

    if not event.reply_to_msg_id:
        return

    msg = await event.get_reply_message()

    # Soporta mensajes de texto Y mensajes con foto (caption)
    content = msg.text or msg.caption or ""

    if not content:
        await event.delete()
        return

    print("CONTENIDO DEL MENSAJE:", content[:80])

    title, links, other = split_message(content)

    data = get_movie(title)

    if not data:
        # Solo avisar si realmente no se encontró
        await event.reply("Película no encontrada")
        return

    new_text = data["text"]

    if links:
        # Insertar el primer link como hipervinculo en el titulo (primera linea)
        first_link = links[0]
        lines = new_text.split("\n")
        lines[0] = f"[{lines[0]}]({first_link})"
        new_text = "\n".join(lines)
        # Si hay links adicionales, agregarlos al final
        if len(links) > 1:
            new_text += "\n\n" + "\n".join(links[1:])

    await client.edit_message(
        event.chat_id,
        msg.id,
        new_text,
        file=data["poster"] if with_poster else None,
        parse_mode="md"
    )

    # Eliminar el mensaje de comando
    await event.delete()

    # Armar link directo al mensaje editado
    import asyncio
    chat_id = str(event.chat_id).replace("-100", "")
    link = f"https://t.me/c/{chat_id}/{msg.id}"

    # Enviar notificacion temporal con link
    notif = await client.send_message(
        event.chat_id,
        f"✅ [Ir al mensaje actualizado]({link})",
        link_preview=False,
        parse_mode="md"
    )

    # Borrar la notificacion despues de 5 segundos
    await asyncio.sleep(5)
    await notif.delete()


# ----------------------------
# COMANDOS: con y sin slash, case insensitive
# ----------------------------

@client.on(events.NewMessage(pattern=r"(?i)^/?info$"))
async def cmd_info(event):
    await handle(event, with_poster=False)


@client.on(events.NewMessage(pattern=r"(?i)^/?infop$"))
async def cmd_infop(event):
    await handle(event, with_poster=True)


client.start()
print("Bot activo...")
client.run_until_disconnected()
