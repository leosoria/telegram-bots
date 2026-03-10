from telethon import TelegramClient, events

api_id = 17877920
api_hash = "4a5893a520b6d4adc40cfa0015b3ecae"

TARGET_CHAT = "My Merges"

client = TelegramClient("session", api_id, api_hash)

media_buffer = []

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handler(event):
    global media_buffer

    chat = await event.get_chat()

    # solo trabajar en el chat MyMerges
    if getattr(chat, "title", "") != TARGET_CHAT:
        return

    msg = event.message

    # guardar foto o video silenciosamente
    if msg.photo or msg.video:
        media_buffer.append(msg)
        print("archivo guardado")

    # comando merge
    if msg.raw_text == "/merge":
        if media_buffer:
            await client.send_file(event.chat_id, media_buffer)
            media_buffer = []
            print("archivos enviados")

client.start()
print("escuchando solo en chat MyMerges...")
client.run_until_disconnected()
