import os
import pymongo
from django.conf import settings

_mongo_client = None
_mongo_db = None


def get_mongo_db():
    """Lazy singleton for MongoDB connection."""
    global _mongo_client, _mongo_db
    if _mongo_db is None:
        uri = getattr(settings, "MONGODB_URI", "mongodb://localhost:27017/")
        db_name = getattr(settings, "MONGODB_DB_NAME", "weighcert")
        try:
            _mongo_client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
            _mongo_db = _mongo_client[db_name]
        except Exception as e:
            # Fallback or error logging
            print(f"Warning: MongoDB connection error: {e}")
            return None
    return _mongo_db

