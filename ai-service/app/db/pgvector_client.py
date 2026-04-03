import json
import os
import psycopg2
from psycopg2 import pool # 👈 Imported pool
from contextlib import contextmanager
from functools import lru_cache 
from loguru import logger

# ---------------------------------------------------
# Connection Pooling
# ---------------------------------------------------

try:
    # ⚡ FIXED: Calling pool directly!
    db_pool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20, # Handles up to 20 concurrent AI requests instantly
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB", "ai_db"),        
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )
    logger.info("✅ Database Connection Pool Created")
except Exception as e:
    logger.error(f"Failed to create DB pool: {e}")
    db_pool = None

@contextmanager
def get_db_connection():
    """Smart context manager that retrieves a connection from the pool and safely returns it."""
    if not db_pool:
        raise Exception("Database pool is not initialized")
    
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn) # Puts it back in the pool for the next user


# ---------------------------------------------------
# Setup Tables (run once)
# ---------------------------------------------------

def setup_vector_tables():
    """
    Creates pgvector extension + tables if they don't exist.
    Run once on app startup.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Table 1: Menu items
            cur.execute("""
                CREATE TABLE IF NOT EXISTS menu_embeddings (
                    id            SERIAL PRIMARY KEY,
                    dish_id       TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    content       TEXT NOT NULL,
                    embedding     vector(384),
                    metadata      JSONB DEFAULT '{}',

                    -- unique constraint so upsert works correctly
                    UNIQUE (dish_id, restaurant_id)
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS menu_embedding_idx
                ON menu_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

            # Table 2: Order history
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_history_embeddings (
                    id            SERIAL PRIMARY KEY,
                    user_id       TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    content       TEXT NOT NULL,
                    embedding     vector(384),
                    metadata      JSONB DEFAULT '{}'
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS order_history_embedding_idx
                ON order_history_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

            # Table 3: Restaurant Profiles
            cur.execute("""
                CREATE TABLE IF NOT EXISTS restaurant_embeddings (
                    id            SERIAL PRIMARY KEY,
                    public_id     TEXT UNIQUE NOT NULL,
                    content       TEXT NOT NULL,
                    embedding     vector(384),
                    metadata      JSONB DEFAULT '{}'
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS restaurant_embedding_idx
                ON restaurant_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

            # Table 4: Table & Zone Profiles
            cur.execute("""
                CREATE TABLE IF NOT EXISTS table_embeddings (
                    id            SERIAL PRIMARY KEY,
                    public_id     TEXT UNIQUE NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    content       TEXT NOT NULL,
                    embedding     vector(384),
                    metadata      JSONB DEFAULT '{}'
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS table_embedding_idx
                ON table_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

             # Table 5: user data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_embeddings (
                    id            SERIAL PRIMARY KEY,
                    user_id       TEXT UNIQUE NOT NULL,
                    content       TEXT NOT NULL,
                    embedding     vector(384),
                    metadata      JSONB DEFAULT '{}'
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS user_embedding_idx
                ON user_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

            conn.commit()
    print("✅ Vector tables ready!")
    

# ---------------------------------------------------
# Insert / Upsert Functions
# ---------------------------------------------------

def insert_menu_item(dish_id, restaurant_id, content, embedding, metadata):
    """Upsert a dish embedding into pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO menu_embeddings
                    (dish_id, restaurant_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (dish_id, restaurant_id)
                DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata;
            """, (
                dish_id,
                restaurant_id,
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ))
            conn.commit()


def insert_order_history(user_id, restaurant_id, content, embedding, metadata):
    """Store one order history embedding into pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO order_history_embeddings
                    (user_id, restaurant_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user_id,
                restaurant_id,
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ))
            conn.commit()


def insert_restaurant_info(public_id, content, embedding, metadata):
    """Upsert restaurant profile into pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO restaurant_embeddings
                    (public_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (public_id)
                DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata;
            """, (
                public_id,
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ))
            conn.commit()


def insert_table_info(public_id, restaurant_id, content, embedding, metadata):
    """Upsert table profile into pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO table_embeddings
                    (public_id, restaurant_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (public_id)
                DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata;
            """, (
                public_id,
                restaurant_id,
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ))
            conn.commit()


def insert_user_info(user_id, content, embedding, metadata):
    """Upserts user profile into pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_embeddings
                    (user_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata;
            """, (
                user_id,
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ))
            conn.commit()


# ---------------------------------------------------
# Search Functions
# ---------------------------------------------------

def search_menu(query_embedding, restaurant_id, top_k=5):
    """
    Find top_k most similar dishes to the query embedding.
    Only returns available dishes.
    Uses cosine similarity — closer = more relevant.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    dish_id,
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM menu_embeddings
                WHERE restaurant_id = %s
                  AND (metadata->>'available')::boolean IS DISTINCT FROM false
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, restaurant_id, query_embedding, top_k))
            results = cur.fetchall()

    return [
        {
            "dish_id":    row[0],
            "content":    row[1],
            "metadata":   row[2],
            "similarity": float(row[3]),
        }
        for row in results
    ]


def search_order_history(query_embedding, user_id, top_k=3):
    """Find past orders similar to the current query."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    user_id,
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM order_history_embeddings
                WHERE user_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, user_id, query_embedding, top_k))
            results = cur.fetchall()

    return [
        {
            "user_id":    row[0],
            "content":    row[1],
            "metadata":   row[2],
            "similarity": float(row[3]),
        }
        for row in results
    ]


# ---------------------------------------------------
# Version Guard Functions (used by Kafka handlers)
# ---------------------------------------------------

def get_dish_version(dish_id: str, restaurant_id: str):
    """Returns current version (int) of a dish in pgvector."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT (metadata->>'version')::int
                FROM menu_embeddings
                WHERE dish_id = %s AND restaurant_id = %s
                LIMIT 1;
            """, (dish_id, restaurant_id))
            row = cur.fetchone()

    return row[0] if row else None


def update_dish_version(dish_id: str, restaurant_id: str, version: int):
    """Update version in metadata after successful ingest."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE menu_embeddings
                SET metadata = metadata || %s::jsonb
                WHERE dish_id = %s AND restaurant_id = %s;
            """, (
                json.dumps({"version": version}),
                dish_id,
                restaurant_id,
            ))
            conn.commit()


def mark_dish_unavailable(dish_id: str, restaurant_id: str, version: int):
    """Soft delete — mark dish as unavailable + update version."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE menu_embeddings
                SET metadata = metadata || %s::jsonb
                WHERE dish_id = %s AND restaurant_id = %s;
            """, (
                json.dumps({"available": False, "version": version}),
                dish_id,
                restaurant_id,
            ))
            conn.commit()


def get_order_metadata(order_id: str, restaurant_id: str) -> dict:
    """Retrieves the metadata JSON for a specific order from the vector DB."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT metadata 
                FROM order_history_embeddings 
                WHERE metadata->>'order_id' = %s AND restaurant_id = %s
                LIMIT 1;
            """, (order_id, restaurant_id))
            row = cur.fetchone()

    if row:
        metadata = row[0]
        if isinstance(metadata, str):
            return json.loads(metadata)
        return metadata
    return None


def update_order_record(order_id: str, restaurant_id: str, content: str, embedding: list, metadata):
    """Updates an existing order's text content, vector embedding, and JSON metadata."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE order_history_embeddings 
                SET content = %s, 
                    embedding = %s, 
                    metadata = %s::jsonb
                WHERE metadata->>'order_id' = %s AND restaurant_id = %s;
            """, (
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
                order_id,
                restaurant_id
            ))
            conn.commit()


def get_table_metadata(table_public_id: str, restaurant_id: str) -> dict:
    """Retrieves the metadata JSON for a specific table from the vector DB."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT metadata 
                FROM table_embeddings 
                WHERE public_id = %s AND restaurant_id = %s
                LIMIT 1;
            """, (table_public_id, restaurant_id))
            row = cur.fetchone()

    if row:
        metadata = row[0]
        return json.loads(metadata) if isinstance(metadata, str) else metadata
    return None


def update_table_record(table_public_id: str, restaurant_id: str, content: str, embedding: list, metadata):
    """Updates an existing table's text content, vector embedding, and JSON metadata."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE table_embeddings 
                SET content = %s, 
                    embedding = %s, 
                    metadata = %s::jsonb
                WHERE public_id = %s AND restaurant_id = %s;
            """, (
                content,
                embedding,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
                table_public_id,
                restaurant_id
            ))
            conn.commit()


# ⚡ Caching applied to static restaurant data
@lru_cache(maxsize=128)
def get_restaurant_metadata(public_id: str) -> dict:
    """Retrieves the restaurant metadata JSON from the vector DB."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT metadata 
                FROM restaurant_embeddings 
                WHERE public_id = %s 
                LIMIT 1;
            """, (public_id,))
            row = cur.fetchone()

    if row:
        metadata = row[0]
        return json.loads(metadata) if isinstance(metadata, str) else metadata
    return None


# ⚡ Caching applied to static restaurant data
@lru_cache(maxsize=128)
def get_restaurant_profile_db(restaurant_id: str) -> str:
    """Fetches the full text profile of the restaurant."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT content 
                FROM restaurant_embeddings 
                WHERE public_id = %s OR metadata->>'slug' = %s
                LIMIT 1;
            """, (restaurant_id, restaurant_id))
            row = cur.fetchone()

    return row[0] if row else "Restaurant details not found."


def check_table_availability_db(restaurant_id: str, zone_name: str = None) -> list:
    """Finds all tables and their current status, optionally filtered by zone."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if zone_name:
                cur.execute("""
                    SELECT content 
                    FROM table_embeddings 
                    WHERE restaurant_id = %s 
                      AND metadata->>'zone_name' ILIKE %s
                    ORDER BY metadata->>'table_number';
                """, (restaurant_id, f"%{zone_name}%"))
            else:
                cur.execute("""
                    SELECT content 
                    FROM table_embeddings 
                    WHERE restaurant_id = %s
                    ORDER BY metadata->>'table_number';
                """, (restaurant_id,))
            results = cur.fetchall()

    return [row[0] for row in results]


def get_user_metadata(user_id: str) -> dict:
    """Retrieves exact user metadata JSON for injecting into the AI context."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT metadata 
                FROM user_embeddings 
                WHERE user_id = %s
                LIMIT 1;
            """, (user_id,))
            row = cur.fetchone()

    if row:
        metadata = row[0]
        return json.loads(metadata) if isinstance(metadata, str) else metadata
    return None