import logging
import re
import base64
import time
from struct import pack
from difflib import get_close_matches
from datetime import datetime

from hydrogram.file_id import FileId
from pymongo import MongoClient, TEXT, ASCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure

from info import (
    DATA_DATABASE_URL,
    DATABASE_NAME,
    COLLECTION_NAME,
    MAX_BTN,
    USE_CAPTION_FILTER
)

logger = logging.getLogger(__name__)

# =====================================================
# 📦 DATABASE (SINGLE DB – FINAL)
# =====================================================
client = MongoClient(DATA_DATABASE_URL, serverSelectionTimeoutMS=5000)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# =====================================================
# 🚀 DB INDEX TUNING (SAFE + FAST)
# =====================================================
def ensure_indexes(col):
    try:
        col.create_index(
            [("file_name", TEXT), ("caption", TEXT)],
            name="file_text_index"
        )
    except OperationFailure as e:
        logger.warning(f"Index warning: {e}")

    try:
        col.create_index("quality", name="quality_idx")
        col.create_index("updated_at", name="updated_at_idx")
    except OperationFailure:
        pass

ensure_indexes(collection)

# =====================================================
# 📊 COUNTS
# =====================================================
def db_count_documents():
    return collection.estimated_document_count()

# =====================================================
# ⚡ SEARCH CACHE
# =====================================================
SEARCH_CACHE = {}
CACHE_TTL = 60

def cache_get(key):
    v = SEARCH_CACHE.get(key)
    if not v:
        return None
    data, ts = v
    if time.time() - ts > CACHE_TTL:
        SEARCH_CACHE.pop(key, None)
        return None
    return data

def cache_set(key, value):
    SEARCH_CACHE[key] = (value, time.time())

# =====================================================
# 🧠 QUALITY DETECTOR
# =====================================================
def detect_quality(name: str) -> str:
    n = name.lower()
    if "2160" in n or "4k" in n:
        return "2160p"
    if "1080" in n:
        return "1080p"
    if "720" in n:
        return "720p"
    if "480" in n:
        return "480p"
    return "unknown"

# =====================================================
# 🔍 FUZZY FIX
# =====================================================
def fuzzy_fix(query, choices):
    match = get_close_matches(query, choices, n=1, cutoff=0.7)
    return match[0] if match else None

# =====================================================
# 🔎 SEARCH ENGINE
# =====================================================
async def get_search_results(query, offset=0, max_results=MAX_BTN):
    q = query.strip().lower()
    if not q or len(q) < 2:
        return [], "", 0

    cache_key = f"{q}:{offset}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    files = []
    total = 0

    # TEXT SEARCH
    try:
        text_filter = {"$text": {"$search": q}}
        cursor = (
            collection.find(
                text_filter,
                {
                    "file_name": 1,
                    "file_size": 1,
                    "caption": 1,
                    "quality": 1,
                    "score": {"$meta": "textScore"},
                }
            )
            .sort([("score", {"$meta": "textScore"})])
            .skip(offset)
            .limit(max_results)
        )
        files = list(cursor)
        total = collection.count_documents(text_filter)
    except Exception as e:
        logger.error(f"Text search error: {e}")

    # REGEX FALLBACK
    if not files:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        rg_filter = (
            {"$or": [{"file_name": regex}, {"caption": regex}]}
            if USE_CAPTION_FILTER
            else {"file_name": regex}
        )
        cursor = collection.find(rg_filter).skip(offset).limit(max_results)
        files = list(cursor)
        total = collection.count_documents(rg_filter)

    # FUZZY RETRY
    if not files:
        try:
            names = collection.distinct("file_name")
            fix = fuzzy_fix(q, names)
            if fix and fix != q:
                return await get_search_results(fix, offset, max_results)
        except:
            pass

    next_offset = offset + max_results if total > offset + max_results else ""
    result = (files, next_offset, total)
    cache_set(cache_key, result)
    return result

# =====================================================
# 🗑 DELETE FILES
# =====================================================
async def delete_files(query):
    regex = re.compile(re.escape(query), re.IGNORECASE)
    res = collection.delete_many({"file_name": regex})
    return res.deleted_count

# =====================================================
# 📄 FILE DETAILS
# =====================================================
async def get_file_details(file_id):
    return collection.find_one({"_id": file_id})

# =====================================================
# 💾 SAVE / UPDATE FILE
# =====================================================
async def save_file(media):
    file_id = unpack_new_file_id(media.file_id)

    name = re.sub(r"@\w+|[_\-.+]", " ", str(media.file_name or "")).strip()
    cap = re.sub(r"@\w+|[_\-.+]", " ", str(media.caption or "")).strip()
    quality = detect_quality(name)

    doc = {
        "_id": file_id,
        "file_name": name,
        "file_size": media.file_size,
        "caption": cap,
        "quality": quality,
        "updated_at": datetime.utcnow()
    }

    try:
        collection.insert_one(doc)
        return "suc"

    except DuplicateKeyError:
        collection.update_one(
            {"_id": file_id},
            {"$set": {
                "caption": cap,
                "quality": quality,
                "updated_at": datetime.utcnow()
            }}
        )
        return "dup"

    except Exception as e:
        logger.error(f"Save file error: {e}")
        return "err"

# =====================================================
# 🔄 CHANNEL UPDATE HELPERS (🔥 FIXED)
# =====================================================
async def update_file_caption(file_id, new_caption: str):
    if not new_caption:
        return False

    new_caption = re.sub(r"@\w+|[_\-.+]", " ", new_caption).strip()

    res = collection.update_one(
        {"_id": file_id},
        {"$set": {
            "caption": new_caption,
            "updated_at": datetime.utcnow()
        }}
    )
    return res.modified_count > 0


async def update_file_quality(file_id, new_name: str):
    quality = detect_quality(new_name)

    res = collection.update_one(
        {"_id": file_id},
        {"$set": {
            "quality": quality,
            "updated_at": datetime.utcnow()
        }}
    )
    return res.modified_count > 0

# =====================================================
# 🔐 FILE ID UTILS
# =====================================================
def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    return encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash,
        )
    )
