import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENALEX_API_KEY", "")
BASE_URL = "https://api.openalex.org"

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "ai_research.duckdb"

AI_SUBFIELD_ID = "1702"
YEAR_RANGE = (2018, 2025)
MIN_CITATIONS = 5
WORK_TYPE = "article"

WORKS_FILTER = (
    f"topics.subfield.id:{AI_SUBFIELD_ID},"
    f"publication_year:{YEAR_RANGE[0]}-{YEAR_RANGE[1]},"
    f"type:{WORK_TYPE},"
    f"cited_by_count:>{MIN_CITATIONS}"
)

WORKS_SELECT = (
    "id,display_name,publication_year,cited_by_count,"
    "topics,authorships,abstract_inverted_index,referenced_works"
)

PER_PAGE = 100
MAX_CONCURRENT_REQUESTS = 5
BATCH_INSERT_SIZE = 500
