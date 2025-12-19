import re
from hydrogram import enums
from hydrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from utils import get_poster, get_size, get_readable_time, temp
from info import DELETE_TIME, script

async def get_imdb_metadata(search, files, settings):
    """
    IMDb से डेटा लाता है और फॉर्मेट किया हुआ कैप्शन और पोस्टर देता है।
    """
    imdb = await get_poster(search, file=(files[0])['file_name']) if settings["imdb"] else None
    TEMPLATE = settings.get('template', script.IMDB_TEMPLATE)
    
    if imdb:
        cap = TEMPLATE.format(
            query=search,
            title=imdb.get('title'),
            votes=imdb.get('votes'),
            aka=imdb.get("aka"),
            seasons=imdb.get("seasons"),
            box_office=imdb.get('box_office'),
            localized_title=imdb.get('localized_title'),
            kind=imdb.get('kind'),
            imdb_id=imdb.get("imdb_id"),
            cast=imdb.get("cast"),
            runtime=imdb.get("runtime"),
            countries=imdb.get("countries"),
            certificates=imdb.get("certificates"),
            languages=imdb.get("languages"),
            director=imdb.get("director"),
            writer=imdb.get("writer"),
            producer=imdb.get("producer"),
            composer=imdb.get("composer"),
            cinematographer=imdb.get("cinematographer"),
            music_team=imdb.get("music_department"),
            distributors=imdb.get("distributors"),
            release_date=imdb.get('release_date'),
            year=imdb.get('year'),
            genres=imdb.get('genres'),
            poster=imdb.get('poster'),
            plot=imdb.get('plot'),
            rating=imdb.get('rating'),
            url=imdb.get('url'),
            **locals()
        )
    else:
        cap = f"<b>💭 ʜᴇʏ,\n♻️ ʜᴇʀᴇ ɪ ꜰᴏᴜɴᴅ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ {search}...</b>"
    
    return cap, imdb.get('poster') if imdb else None

def get_file_list_string(files, chat_id, offset=1):
    """सर्च रिजल्ट में फाइलों की लिस्ट (links) तैयार करता है।"""
    files_link = ""
    for file_num, file in enumerate(files, start=offset):
        # ✅ फाइल नाम से कचरा (जैसे h4hBYE>) साफ करने के लिए regex फिक्स
        clean_name = re.sub(r'^[a-zA-Z0-9]+>', '', file['file_name']).strip()
        
        files_link += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{chat_id}_{file['_id']}>[{get_size(file['file_size'])}] {clean_name}</a></b>"""
    return files_link

def get_auto_delete_str(settings):
    """Auto-delete की सूचना वाला स्ट्रिंग तैयार करता है।"""
    if settings.get("auto_delete"):
        return f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code> ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs</b>"
    return ""

async def send_metadata_reply(message, cap, poster, reply_markup, settings, files_link):
    """पोस्टर के साथ या बिना पोस्टर के मैसेज भेजने का लॉजिक।"""
    del_msg = get_auto_delete_str(settings)
    
    # टेलीग्राम की 1024 कैप्शन लिमिट को मैनेज करने के लिए ट्रिमिंग
    full_cap = cap[:800] + files_link + del_msg
    
    if poster:
        try:
            return await message.reply_photo(
                photo=poster,
                caption=full_cap,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            poster_low = poster.replace('.jpg', "._V1_UX360.jpg")
            return await message.reply_photo(
                photo=poster_low,
                caption=full_cap,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
        except Exception:
            return await message.reply_text(
                text=full_cap,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                quote=True
            )
    else:
        return await message.reply_text(
            text=full_cap,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            quote=True
        )
