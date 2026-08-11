from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Kevin Zhang kevinlzhang129@gmail.com"
}

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

DB_URL = (
    f"postgresql+psycopg2://"
    f"{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

create_pgvector_table_sql = """
CREATE TABLE IF NOT EXISTS filing_chunks (
    id BIGSERIAL PRIMARY KEY,

    filing_id BIGINT NOT NULL
        REFERENCES sp500_filings(id)
        ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    section TEXT,

    chunk_text TEXT NOT NULL,

    embedding VECTOR(768),

    UNIQUE (filing_id, chunk_index)
);
"""


engine = create_engine(DB_URL)

with engine.begin() as connection:
    connection.execute(text(create_pgvector_table_sql))

print("filing_chunks table created successfully.")

model = SentenceTransformer(
    "nomic-ai/nomic-embed-text-v1.5",
    trust_remote_code=True
)

sample_text = (
    "search_document: "
    "Apple reported increasing demand for its products."
)

embedding = model.encode(sample_text)

print("Embedding shape:", embedding.shape)