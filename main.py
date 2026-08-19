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
        
        # ألغينا التوجيه المباشر، وضفنا أمر (inline) لإجبار المتصفح على العرض وعدم التنزيل
        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": 'inline; filename="video.mp4"'
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

    except Exception as e:
        return web.Response(status=500, text=f"Streaming Error: {str(e)}")
