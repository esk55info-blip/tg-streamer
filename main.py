import os
import asyncio
import aiohttp
from aiohttp import web
from pyrogram import Client, filters
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. الإعدادات الأساسية (البيانات الثابتة)
# ==========================================
API_ID = 35148261
API_HASH = "57bbfcc98eddf401e2cdaa36d3e36a6e"
BOT_TOKEN = "8956444396:AAEaabOQkS8X9GxuWT64NhZ80gqYMYqYsOo"
CHANNEL_ID = -1004357723672
SERVER_DOMAIN = "https://tg-streamer-production-80b4.up.railway.app" # رابطك الثابت

# ==========================================
# 2. ربط قاعدة بيانات فايربيس (Firestore)
# ==========================================
db = None
try:
    # يجب رفع ملف firebase-adminsdk-key.json إلى مشروعك لاحقاً ليعمل الرفع التلقائي
    if os.path.exists("firebase-adminsdk-key.json"):
        cred = credentials.Certificate("firebase-adminsdk-key.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ تم الاتصال بـ Firebase بنجاح!")
    else:
        print("⚠️ ملف firebase-adminsdk-key.json غير موجود. السيرفر سيعمل لكن الرفع التلقائي متوقف.")
except Exception as e:
    print(f"❌ خطأ في ربط Firebase: {e}")

# ==========================================
# 3. إعداد عميل تيليجرام (Pyrogram)
# ==========================================
app = Client("stream_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
routes = web.RouteTableDef()

# ==========================================
# 4. المراقب التلقائي (Auto-Uploader)
# ==========================================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def auto_upload_to_firebase(client, message):
    if not db:
        return # إذا فايربيس مامربوط، تجاهل العملية

    try:
        caption = message.caption or ""
        # يبحث عن كلمة tmdb: متبوعة برقم الفيلم في وصف الفيديو
        if "tmdb:" in caption.lower():
            tmdb_id = caption.lower().split("tmdb:")[1].strip().split()[0]
            message_id = message.id
            
            # توليد الرابط مع خدعة ?v=1 لتجاوز الكاش
            stream_url = f"{SERVER_DOMAIN}/stream/{message_id}?v=1"
            
            # رفع البيانات إلى Firestore
            doc_ref = db.collection('movies').document(tmdb_id)
            doc_ref.set({
                'tmdb_id': tmdb_id,
                'stream_url': stream_url,
                'message_id': message_id,
                'file_size': message.video.file_size if message.video else message.document.file_size,
                'timestamp': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            print(f"🎬 تم ربط الفيلم ورفعه إلى فايربيس بنجاح! TMDB ID: {tmdb_id}")
    except Exception as e:
        print(f"❌ حدث خطأ أثناء الرفع التلقائي: {e}")

# ==========================================
# 5. مسارات الويب (سيرفر البث)
# ==========================================
@routes.get("/")
async def home(request):
    return web.Response(text="Server is running securely and actively streaming!")

@routes.get("/info/{message_id}")
async def info(request):
    try:
        msg_id = int(request.match_info["message_id"])
        msg = await app.get_messages(CHANNEL_ID, msg_id)
        media = msg.video or msg.document or msg.animation
        if not media: return web.Response(text="لا يوجد فيديو في هذه الرسالة")
        return web.json_response({
            "Status": "البوت يعمل بنجاح!",
            "File_Size_Bytes": media.file_size,
            "Mime_Type": getattr(media, "mime_type", "unknown")
        })
    except Exception as e:
        return web.Response(text=f"مشكلة: {str(e)}")

@routes.get("/stream/{message_id}")
async def stream_media(request):
    try:
        message_id = int(request.match_info["message_id"])
        msg = await app.get_messages(CHANNEL_ID, message_id)
        
        media = msg.video or msg.document or msg.animation
        if not msg or not media:
            return web.Response(status=404, text="Media Not Found")
        
        file_size = media.file_size
        
        # --- التسريع المباشر للمقاطع القصيرة (أقل من 20 ميجا) ---
        if file_size < 20 * 1024 * 1024:
            file_id = media.file_id
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        file_path = data["result"]["file_path"]
                        direct_link = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                        raise web.HTTPFound(direct_link)

        # --- نظام البث الثقيل للأفلام والملفات الكبيرة (أكبر من 20 ميجا) ---
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*", # للسماح بتشغيله من أي تطبيق
        }

        range_header = request.headers.get("Range")
        if range_header:
            range_val = range_header.replace("bytes=", "").split("-")
            from_byte = int(range_val[0])
            to_byte = int(range_val[1]) if len(range_val) > 1 and range_val[1] else file_size - 1
            to_byte = min(to_byte, file_size - 1)
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
                # سحب البيانات بشكل كتل متوازية لتقليل الضغط
                async for chunk in app.stream_media(msg, offset=offset_chunk):
                    if first:
                        chunk = chunk[skip:]
                        first = False
                    if len(chunk) > length:
                        await response.write(chunk[:length])
                        break
                    await response.write(chunk)
                    length -= len(chunk)
            except (asyncio.CancelledError, ConnectionResetError):
                # تجاوز ذكي لقطوعات AVPlayer لتجنب انهيار السيرفر (Deadlock)
                pass
            return response

        else:
            headers["Content-Length"] = str(file_size)
            response = web.StreamResponse(status=200, headers=headers)
            await response.prepare(request)
            try:
                async for chunk in app.stream_media(msg):
                    await response.write(chunk)
            except (asyncio.CancelledError, ConnectionResetError):
                pass
            return response

    except web.HTTPFound:
        raise
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
