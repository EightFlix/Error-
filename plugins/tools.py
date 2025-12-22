import os
import aiohttp
import asyncio
import time
from typing import Optional, Dict

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from info import ADMINS
from utils import is_premium

# =========================
# CONFIG FOR KOYEB
# =========================
MAX_CONCURRENT_UPLOADS = 1  # Limit for free server
CHUNK_SIZE = 128 * 1024  # 128KB chunks (lighter than 256KB)
PROGRESS_UPDATE_INTERVAL = 2  # Update every 2 seconds
SESSION_TIMEOUT = 300  # 5 minutes
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit for free tier

GOFILE_API = "https://store1.gofile.io/contents/uploadfile"

# =========================
# GLOBAL STATE (MEMORY EFFICIENT)
# =========================
UPLOAD_QUEUE = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
UPLOAD_PANEL: Dict[int, Dict] = {}
ACTIVE_UPLOADS: Dict[int, bool] = {}

# =========================
# CLEANUP OLD SESSIONS
# =========================
async def cleanup_sessions():
    """Remove expired sessions to save memory"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        now = time.time()
        expired = [
            uid for uid, state in UPLOAD_PANEL.items()
            if now - state.get("created", now) > SESSION_TIMEOUT
        ]
        for uid in expired:
            UPLOAD_PANEL.pop(uid, None)
            ACTIVE_UPLOADS.pop(uid, None)

# Start cleanup task
asyncio.create_task(cleanup_sessions())

# =========================
# UI BUTTONS
# =========================
def panel_buttons(state: Dict) -> InlineKeyboardMarkup:
    """Generate upload panel buttons"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🔒 Private {'✅' if state.get('private') else '❌'}",
                callback_data="up#private"
            )
        ],
        [
            InlineKeyboardButton("🗑 10 Min", callback_data="up#del#600"),
            InlineKeyboardButton("🗑 30 Min", callback_data="up#del#1800")
        ],
        [
            InlineKeyboardButton("🚀 Upload", callback_data="up#start"),
            InlineKeyboardButton("❌ Cancel", callback_data="up#cancel")
        ]
    ])

# =========================
# EFFICIENT PROGRESS TRACKER
# =========================
class ProgressTracker:
    """Memory-efficient progress tracker"""
    
    def __init__(self, total_size: int, status_msg):
        self.total = total_size
        self.sent = 0
        self.start = time.time()
        self.status = status_msg
        self.last_update = 0
        self.cancelled = False
    
    async def update(self, chunk_size: int):
        """Update progress with rate limiting"""
        self.sent += chunk_size
        now = time.time()
        
        # Rate limit updates
        if now - self.last_update < PROGRESS_UPDATE_INTERVAL:
            return
        
        elapsed = now - self.start
        if elapsed < 1:
            return
        
        percent = (self.sent / self.total) * 100
        speed = self.sent / elapsed / 1024  # KB/s
        remaining = self.total - self.sent
        eta = int(remaining / (speed * 1024 + 1))
        
        # Format sizes
        sent_mb = self.sent / (1024 * 1024)
        total_mb = self.total / (1024 * 1024)
        
        text = (
            "⚡ **Uploading...**\n\n"
            f"📊 `{percent:.1f}%` ({sent_mb:.1f}/{total_mb:.1f} MB)\n"
            f"🚀 `{speed:.1f} KB/s`\n"
            f"⏳ `{eta}s remaining`"
        )
        
        try:
            await self.status.edit(text)
            self.last_update = now
        except Exception:
            pass

# =========================
# STREAMING UPLOAD (MEMORY EFFICIENT)
# =========================
async def stream_file_upload(
    file_path: str,
    tracker: ProgressTracker
) -> aiohttp.FormData:
    """Stream file in chunks to avoid loading entire file in memory"""
    
    async def file_sender():
        with open(file_path, 'rb') as f:
            while not tracker.cancelled:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                await tracker.update(len(chunk))
                yield chunk
    
    data = aiohttp.FormData()
    data.add_field(
        'file',
        file_sender(),
        filename=os.path.basename(file_path),
        content_type='application/octet-stream'
    )
    
    return data

# =========================
# /upload COMMAND
# =========================
@Client.on_message(filters.command("upload") & filters.private)
async def upload_panel(bot: Client, message):
    """Initialize upload panel"""
    uid = message.from_user.id
    
    # Check if already uploading
    if ACTIVE_UPLOADS.get(uid):
        return await message.reply("⚠️ You already have an active upload!")
    
    # Permission check
    if uid not in ADMINS and not await is_premium(uid, bot):
        return await message.reply("❌ Upload is Premium only.")
    
    # Validate reply
    if not message.reply_to_message or not message.reply_to_message.media:
        return await message.reply("❗ Reply to a file to upload")
    
    media = message.reply_to_message
    
    # Check file size (for free tier)
    file_size = getattr(media.document or media.video or media.audio, 'file_size', 0)
    if file_size > MAX_FILE_SIZE:
        return await message.reply(
            f"❌ File too large!\n"
            f"Max: {MAX_FILE_SIZE / (1024*1024):.0f}MB"
        )
    
    # Create session
    UPLOAD_PANEL[uid] = {
        "file": media,
        "private": False,
        "delete": 0,
        "created": time.time(),
        "file_size": file_size
    }
    
    await message.reply(
        "📤 **Upload Panel**\n\n"
        f"📁 Size: {file_size / (1024*1024):.1f} MB\n"
        "Configure and start upload.",
        reply_markup=panel_buttons(UPLOAD_PANEL[uid])
    )

# =========================
# CALLBACK HANDLER
# =========================
@Client.on_callback_query(filters.regex("^up#"))
async def upload_panel_cb(bot: Client, query: CallbackQuery):
    """Handle panel button callbacks"""
    uid = query.from_user.id
    
    # Validate session
    if uid not in UPLOAD_PANEL:
        return await query.answer("⚠️ Session expired!", show_alert=True)
    
    state = UPLOAD_PANEL[uid]
    data = query.data.split("#")
    
    # Handle actions
    if data[1] == "private":
        state["private"] = not state["private"]
        await query.message.edit_reply_markup(panel_buttons(state))
        await query.answer()
    
    elif data[1] == "del":
        state["delete"] = int(data[2])
        await query.answer(f"✅ Auto-delete: {int(data[2])//60} min")
    
    elif data[1] == "cancel":
        UPLOAD_PANEL.pop(uid, None)
        await query.message.edit("❌ Upload cancelled.")
    
    elif data[1] == "start":
        # Check if already uploading
        if ACTIVE_UPLOADS.get(uid):
            return await query.answer("⚠️ Already uploading!", show_alert=True)
        
        await query.message.edit("⏳ Preparing upload...")
        
        # Start upload in background (non-blocking)
        asyncio.create_task(start_upload(bot, query.message, uid))

# =========================
# MAIN UPLOAD LOGIC (OPTIMIZED)
# =========================
async def start_upload(bot: Client, msg, uid: int):
    """Handle file upload with progress tracking"""
    
    # Acquire semaphore (limit concurrent uploads)
    async with UPLOAD_QUEUE:
        state = UPLOAD_PANEL.get(uid)
        if not state:
            return await msg.edit("❌ Session expired.")
        
        # Mark as active
        ACTIVE_UPLOADS[uid] = True
        file_path: Optional[str] = None
        
        try:
            media = state["file"]
            
            # Download with timeout
            status = await msg.edit("📥 Downloading...")
            
            try:
                file_path = await asyncio.wait_for(
                    media.download(),
                    timeout=120  # 2 minute timeout
                )
            except asyncio.TimeoutError:
                return await msg.edit("❌ Download timeout!")
            
            if not file_path or not os.path.exists(file_path):
                return await msg.edit("❌ Download failed!")
            
            # Get actual file size
            file_size = os.path.getsize(file_path)
            
            # Create progress tracker
            await msg.edit("⚡ Starting upload...")
            tracker = ProgressTracker(file_size, msg)
            
            # Upload with streaming
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=600)  # 10 min timeout
            ) as session:
                
                # Prepare streaming data
                data = await stream_file_upload(file_path, tracker)
                
                # Upload
                async with session.post(GOFILE_API, data=data) as response:
                    if response.status != 200:
                        return await msg.edit(f"❌ Upload failed! Status: {response.status}")
                    
                    result = await response.json()
            
            # Check result
            if result.get("status") != "ok":
                error = result.get("message", "Unknown error")
                return await msg.edit(f"❌ Upload failed: {error}")
            
            # Get download link
            link = result["data"]["downloadPage"]
            file_name = os.path.basename(file_path)
            
            # Success message
            await msg.edit(
                f"✅ **Upload Complete!**\n\n"
                f"📁 `{file_name}`\n"
                f"📊 `{file_size / (1024*1024):.1f} MB`\n\n"
                f"🔗 <code>{link}</code>",
                disable_web_page_preview=True
            )
        
        except asyncio.CancelledError:
            await msg.edit("❌ Upload cancelled!")
        
        except aiohttp.ClientError as e:
            await msg.edit(f"❌ Network error: {str(e)[:50]}")
        
        except Exception as e:
            await msg.edit(f"❌ Error: {str(e)[:100]}")
        
        finally:
            # Cleanup
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            
            # Remove from tracking
            UPLOAD_PANEL.pop(uid, None)
            ACTIVE_UPLOADS.pop(uid, None)

# =========================
# CANCEL COMMAND (OPTIONAL)
# =========================
@Client.on_message(filters.command("cancel_upload") & filters.private)
async def cancel_upload(bot: Client, message):
    """Cancel active upload"""
    uid = message.from_user.id
    
    if uid not in ACTIVE_UPLOADS:
        return await message.reply("❌ No active upload!")
    
    UPLOAD_PANEL.pop(uid, None)
    ACTIVE_UPLOADS.pop(uid, None)
    
    await message.reply("✅ Upload cancelled!")
