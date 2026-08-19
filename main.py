import os
from aiohttp import web
from pyrogram import Client

API_ID = 35148261
API_HASH = "57bbfcc98eddf401e2cdaa36d3e36a6e"
BOT_TOKEN = "8956444396:AAEaabOQkS8X9GxuWT64NhZ80gqYMYqYsOo"
CHANNEL_ID = -1004357723672

app = Client("stream_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="Server is running successfully!")

# مسار الفحص الجديد (X-Ray) لمعرفة حالة البوت
@routes.get("/info/{message_id}")
async def info(request):
    try:
        msg_id = int(request.match_info["message_id"])
        msg = await app.get_messages(CHANNEL_ID, msg_id)
        if not msg: return web.Response(text="الرسالة غير موجودة أو البوت مو أدمن بالقناة")
        media = msg.video or msg.document or msg.animation
        if not media: return web.Response(text="لا يوجد فيديو في هذه الرسالة")
        return web.json_response({
            "Status": "البوت يعمل بنجاح ومتصل بتيليجرام!",
            "File_Size_Bytes": media.file_size,
            "Mime_Type": getattr(media, "mime_type", "unknown")
        })
    except Exception as e:
        return web.Response(text=f"مشكلة في اتصال البوت: {str(e)}")

@routes.get("/stream/{message_id}")
async def stream_media(request):
    try:
        message_id = int(request.match_info["message_id"])
        msg = await app.get_messages(CHANNEL_ID, message_id)
        
        media = msg.video or msg.document or msg.animation
        if not msg or not media:
            return web.Response(status=404, text="Media Not Found")
        
        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        
        headers = {
            "Content-Length": str(file_size),
            "Content-Type": mime_type,
            "Content-Disposition": 'inline; filename="video.mp4"',
            "Accept-Ranges": "bytes"
        }

        range_header = request.headers.get("Range")
        if range_header:
            range_val = range_header.replace("bytes=", "").split("-")
            from_byte = int(range_val[0])
            to_byte = int(range_val[1]) if len(range_val) > 1 and range_val[1] else file_size - 1
            length = to_byte - from_byte + 1
            
            headers["Content-Range"] = f"bytes {from_byte}-{to_byte}/{file_size}"
            headers["Content-Length"] = str(length)
            
            response = web.StreamResponse(status=206, headers=headers)
            await response.prepare(request)
            
            chunk_size = 1024 * 1024
            offset_chunk = from_byte // chunk_size
            skip = from_byte % chunk_size

            first = True
            try:
                async for chunk in app.stream_media(msg, offset=offset_chunk):
                    if first:
                        chunk = chunk[skip:]
                        first = False
                    
                    if len(chunk) > length:
                        await response.write(chunk[:length])
                        break
                    await response.write(chunk)
                    length -= len(chunk)
            except Exception:
                pass
            return response
        else:
            response = web.StreamResponse(status=200, headers=headers)
            await response.prepare(request)
            try:
                async for chunk in app.stream_media(msg):
                    await response.write(chunk)
            except Exception:
                pass
            return response

    except Exception as e:
        return web.Response(status=500, text=f"Streaming Error: {str(e)}")

async def init_app():
    await app.start()
    app_web = web.Application()
    app_web.add_routes(routes)
    return app_web

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(init_app(), port=port)
