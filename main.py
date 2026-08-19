from aiohttp import web
from pyrogram import Client

# بياناتك مدمجة مباشرة
API_ID = 35148261
API_HASH = "57bbfcc98eddf401e2cdaa36d3e36a6e"
BOT_TOKEN = "8956444396:AAEaabOQkS8X9GxuWT64NhZ80gqYMYqYsOo"
CHANNEL_ID = -1004357723672

app = Client("stream_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="Server is running successfully!")

@routes.get("/stream/{message_id}")
async def stream_media(request):
    message_id = int(request.match_info["message_id"])
    msg = await app.get_messages(CHANNEL_ID, message_id)
    
    if not msg or not msg.video:
        return web.Response(status=404, text="Video Not Found")
    
    file_size = msg.video.file_size
    range_header = request.headers.get("Range")

    if range_header:
        byte_range = range_header.replace("bytes=", "").split("-")
        from_byte = int(byte_range[0])
        to_byte = int(byte_range[1]) if byte_range[1] else file_size - 1
        length = to_byte - from_byte + 1

        headers = {
            "Content-Range": f"bytes {from_byte}-{to_byte}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": msg.video.mime_type or "video/mp4",
        }
        response = web.StreamResponse(status=206, headers=headers)
        await response.prepare(request)

        async for chunk in app.stream_media(msg, offset=from_byte, limit=length):
            await response.write(chunk)
        return response

    headers = {
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes",
        "Content-Type": msg.video.mime_type or "video/mp4",
    }
    response = web.StreamResponse(headers=headers)
    await response.prepare(request)

    async for chunk in app.stream_media(msg):
        await response.write(chunk)
    return response

async def init_app():
    await app.start()
    web_app = web.Application()
    web_app.add_routes(routes)
    return web_app

if __name__ == "__main__":
    web.run_app(init_app(), port=8080)
