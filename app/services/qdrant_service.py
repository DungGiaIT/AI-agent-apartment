import logging
# pyrefly: ignore [missing-import]
from qdrant_client import QdrantClient
# pyrefly: ignore [missing-import]
from qdrant_client.http import models
from app.core.config import settings

logger = logging.getLogger(__name__)

# Khởi tạo Qdrant Client
try:
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    logger.info(f"Connected to Qdrant at {settings.qdrant_url}")
except Exception as e:
    logger.error(f"Failed to connect to Qdrant: {e}")
    qdrant_client = None

def init_qdrant_collections():
    """
    Tạo các collections cần thiết nếu chưa tồn tại.
    """
    if not qdrant_client:
        return
        
    collection_name = "apartments"
    try:
        collections = qdrant_client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        
        if not exists:
            logger.info(f"Creating Qdrant collection: {collection_name}")
            # Mặc định vector size cho gemini text-embedding-004 là 768
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=768, 
                    distance=models.Distance.COSINE
                ),
            )
            logger.info(f"Collection {collection_name} created successfully.")
        else:
            logger.info(f"Collection {collection_name} already exists.")
    except Exception as e:
        logger.error(f"Error initializing Qdrant collection: {e}")
