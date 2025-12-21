import logging
import re
import base64
import time
from struct import pack
from difflib import get_close_matches
from hydrogram.file_id import FileId
from pymongo import MongoClient, TEXT
from pymongo.errors import DuplicateKeyError, OperationFailure
from info import (
    USE_CAPTION_FILTER,
    FILES_DATABASE_URL,
    SECOND_FILES_DATABASE_URL,
    DATABASE_NAME,
    COLLECTION_NAME,
    MAX_BTN
)

logger = logging.getLogger(__name__)

# ================= DATABASE =================
client = MongoClient(FILES_DATABASE_URL, serverSelectionTimeoutMS=5000)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

second_collection = None
if SECOND_FILES_DATABASE_URL:
    second_client = MongoClient(SECOND_FILES_DATABASE_URL, serverSelectionTimeoutMS=5000)
    second_db = second_client[DATABASE_NAME]
    second_collection = second_db[COLLECTION_NAME]

# ================= SAFE TEXT INDEX =================
def ensure_text_index(col, name="file_name_text"):
    try:
        col.create_index([("file_name", TEXT)], name=name)
    except OperationFailure:
        pass

ensure_text_index(collection)
if second_collection is not None:
    ensure_text_index(second_collection)

# ================= ULTRA CACHE =================
SEARCH_CACHE = {}
CACHE_TTL = 60  # seconds

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

# ================= TYPO FIX =================
def typo_fix(query, choices):
    match = get_close_matches(query, choices, n=1, cutoff=0.75)
    return match[0] if match else None

# ================= SEARCH =================
async def get_search_results(query, offset=0, max_results=MAX_BTN, lang=None):
    q = query.strip().lower()
    if not q or len(q) < 2:
        return [], "", 0

    cache_key = f"{q}:{offset}:{lang}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    files = []
    total = 0

    # ---------- TEXT SEARCH ----------
    text_filter = {"$text": {"$search": q}}
    projection = {
        "file_name": 1,
        "file_size": 1,
        "caption": 1,
        "score": {"$meta": "textScore"}
    }

    try:
        cur = collection.find(
            text_filter, projection
        ).sort([("score", {"$meta": "textScore"})]) \
         .skip(offset).limit(max_results)

        files = list(cur)
        total = collection.count_documents(text_filter)

        if second_collection is not None:
            cur2 = second_collection.find(
                text_filter, projection
            ).sort([("score", {"$meta": "textScore"})]) \
             .skip(offset).limit(max_results)

            files.extend(list(cur2))
            total += second_collection.count_documents(text_filter)
    except Exception:
        files = []

    # ---------- REGEX FALLBACK ----------
    if not files:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        rg_filter = (
            {"$or": [{"file_name": regex}, {"caption": regex}]}
            if USE_CAPTION_FILTER
            else {"file_name": regex}
        )

        cur = collection.find(rg_filter).skip(offset).limit(max_results)
        files = list(cur)
        total = collection.count_documents(rg_filter)

        if second_collection is not None:
            cur2 = second_collection.find(rg_filter).skip(offset).limit(max_results)
            files.extend(list(cur2))
            total += second_collection.count_documents(rg_filter)

    # ---------- TYPO RETRY ----------
    if not files:
        titles = collection.distinct("file_name")
        fix = typo_fix(q, titles)
        if fix and fix != q:
            return await get_search_results(fix, offset, max_results, lang)

    # ---------- LANGUAGE FILTER ----------
    if lang:
        files = [f for f in files if lang in f.get("file_name", "").lower()]
        total = len(files)

    next_offset = offset + max_results if total > offset + max_results else ""
    result = (files[:max_results], next_offset, total)
    cache_set(cache_key, result)
    return result

# ================= SAVE FILE =================
async def save_file(media):
    file_id = unpack_new_file_id(media.file_id)
    name = re.sub(r"@\w+|[_\-.+]", " ", str(media.file_name or ""))
    cap = re.sub(r"@\w+|[_\-.+]", " ", str(media.caption or ""))

    doc = {
        "_id": file_id,
        "file_name": name,
        "file_size": media.file_size,
        "caption": cap
    }

    try:
        collection.insert_one(doc)
        return "suc"
    except DuplicateKeyError:
        return "dup"
    except OperationFailure:
        if second_collection is not None:
            try:
                second_collection.insert_one(doc)
                return "suc"
            except DuplicateKeyError:
                return "dup"
        return "err"

# ================= FILE DETAILS =================
async def get_file_details(file_id):
    doc = collection.find_one({"_id": file_id})
    if not doc and second_collection is not None:
        doc = second_collection.find_one({"_id": file_id})
    return doc

# ================= FILE ID UTILS =================
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
            decoded.access_hash
        )
    )
