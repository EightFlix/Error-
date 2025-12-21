import logging
import re
import base64
from struct import pack
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

# ================= DATABASE CONNECTION =================
client = MongoClient(FILES_DATABASE_URL)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

second_collection = None
if SECOND_FILES_DATABASE_URL:
    second_client = MongoClient(SECOND_FILES_DATABASE_URL)
    second_db = second_client[DATABASE_NAME]
    second_collection = second_db[COLLECTION_NAME]

# ================= SAFE TEXT INDEX =================
def ensure_text_index(col, name="file_name_text"):
    try:
        col.create_index(
            [("file_name", TEXT)],
            name=name
        )
        logger.info("TEXT index created")
    except OperationFailure as e:
        # Index already exists with different options → ignore safely
        if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
            logger.info("TEXT index already exists, skipping")
        else:
            raise e

ensure_text_index(collection)
if second_collection:
    ensure_text_index(second_collection)

# ================= COUNT =================
def db_count_documents():
    return collection.count_documents({})

def second_db_count_documents():
    if second_collection:
        return second_collection.count_documents({})
    return 0

# ================= SAVE FILE =================
async def save_file(media):
    file_id = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"@\w+|[_\-.+]", " ", str(media.file_name))
    caption = re.sub(r"@\w+|[_\-.+]", " ", str(media.caption))

    document = {
        "_id": file_id,
        "file_name": file_name,
        "file_size": media.file_size,
        "caption": caption
    }

    try:
        collection.insert_one(document)
        return "suc"
    except DuplicateKeyError:
        return "dup"
    except OperationFailure:
        if second_collection:
            try:
                second_collection.insert_one(document)
                return "suc"
            except DuplicateKeyError:
                return "dup"
        return "err"

# ================= SEARCH =================
async def get_search_results(query, offset=0, max_results=MAX_BTN, lang=None):
    query = query.strip().lower()
    if not query or len(query) < 2:
        return [], "", 0

    files = []
    total = 0

    # ---------- TEXT SEARCH (FAST) ----------
    text_filter = {"$text": {"$search": query}}
    projection = {"score": {"$meta": "textScore"}}

    try:
        cursor = collection.find(
            text_filter, projection
        ).sort(
            [("score", {"$meta": "textScore"})]
        ).skip(offset).limit(max_results)

        files = list(cursor)
        total = collection.count_documents(text_filter)

        if second_collection:
            cursor2 = second_collection.find(
                text_filter, projection
            ).sort(
                [("score", {"$meta": "textScore"})]
            ).skip(offset).limit(max_results)

            files.extend(list(cursor2))
            total += second_collection.count_documents(text_filter)
    except Exception:
        files = []

    # ---------- REGEX FALLBACK (SAFE) ----------
    if not files:
        regex = re.compile(re.escape(query), re.IGNORECASE)
        if USE_CAPTION_FILTER:
            rg_filter = {"$or": [{"file_name": regex}, {"caption": regex}]}
        else:
            rg_filter = {"file_name": regex}

        cursor = collection.find(rg_filter).skip(offset).limit(max_results)
        files = list(cursor)
        total = collection.count_documents(rg_filter)

        if second_collection:
            cursor2 = second_collection.find(rg_filter).skip(offset).limit(max_results)
            files.extend(list(cursor2))
            total += second_collection.count_documents(rg_filter)

    # ---------- LANGUAGE FILTER ----------
    if lang:
        files = [f for f in files if lang in f.get("file_name", "").lower()]
        total = len(files)

    next_offset = offset + max_results if total > offset + max_results else ""
    return files[:max_results], next_offset, total

# ================= DELETE =================
async def delete_files(query):
    query = query.strip().lower()
    regex = re.compile(re.escape(query), re.IGNORECASE)

    result1 = collection.delete_many({"file_name": regex})
    total = result1.deleted_count

    if second_collection:
        result2 = second_collection.delete_many({"file_name": regex})
        total += result2.deleted_count

    return total

# ================= FILE DETAILS =================
async def get_file_details(file_id):
    file = collection.find_one({"_id": file_id})
    if not file and second_collection:
        file = second_collection.find_one({"_id": file_id})
    return file

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
