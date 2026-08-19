from aiohttp import web
from pyrogram import Client

API_ID = 35148261
API_HASH = "57bbfcc98eddf401e2cdaa36d3e36a6e"
BOT_TOKEN = "8956444396:AAEaabOQkS8X9GxuWT64NhZ80gqYMYqYsOo"
CHANNEL_ID = -1004357723672

# استخدام in_memory يمنع مشاكل تعليق السيرفر عند إعادة التشغيل
app = Client("stream_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="Server is running successfully!")

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
        range_header = request.headers.get("Range")

        if range_header:
            range_val = range_header.replace("bytes=", "").split("-")
            from_byte = int(range_val[0]) if range_val[0] else 0
            to_byte = int(range_val[1]) if len(range_val) > 1 and range_val[1] else file_size - 1
            to_byte = min(to_byte, file_size - 1)
            length = to_byte - from_byte + 1

            headers = {
                "Content-Range": f"bytes {from_byte}-{to_byte}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": mime_type,
                "Access-Control-Allow-Origin": "*",
            }
            response = web.StreamResponse(status=206, headers=headers)
            await response.prepare(request)

            # --- الخدعة هنا: القفز المباشر إلى الجزء المطلوب ---
            # مكتبة تيليجرام تسحب البيانات على شكل كتل (1 ميجابايت)
            chunk_size = 1024 * 1024 
            offset_chunk = from_byte // chunk_size # تحديد رقم الكتلة المطلوبة فوراً
            skip_bytes = from_byte % chunk_size    # البايتات الزائدة في البداية

            try:
                first_chunk = True
                bytes_sent = 0
                
                # القفز فوراً إلى الكتلة (offset) بدون تحميل ما قبلها
                async for chunk in app.stream_media(msg, offset=offset_chunk):
                    if first_chunk:
                        chunk = chunk[skip_bytes:]
                        first_chunk = False
                    
                    chunk_length = len(chunk)
                    
                    # إيقاف السحب إذا اكتمل الجزء المطلوب لتوفير الموارد
                    if bytes_sent + chunk_length > length:
                        allowed_chunk = length - bytes_sent
                        await response.write(chunk[:allowed_chunk])
                        break
                        
                    await response.write(chunk)
                    bytes_sent += chunk_length
                    
            except Exception:
                # تجاهل أخطاء قطع الاتصال الطبيعية من مشغل آبل
                pass
            return response

        # إذا لم يكن هناك Range (تشغيل عادي)
        headers = {
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": mime_type,
            "Access-Control-Allow-Origin": "*",
        }
        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        try:
            async for chunk in app.stream_media(msg):
                await response.write(chunk)
        except Exception:
            pass
        return response

    except Exception as e:
        return web.Response(status=500, text=f"Error: {str(e)}")

async def init_app():
    await app.start()
    web_app = web.Application(client_max_size=1024**3)
    web_app.add_routes(routes)
    return web_app

if __name__ == "__main__":
    web.run_app(init_app(), port=8080)
