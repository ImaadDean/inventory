from pymongo import ReturnDocument
from app.config.database import get_database

async def get_next_sequence_value(sequence_name: str):
    db = await get_database()
    sequence_document = await db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"sequence_value": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )
    return sequence_document["sequence_value"]
