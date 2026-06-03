import asyncio
import json
import logging
import os
import sqlite3
from typing import Dict, List, Set, Tuple
import aiohttp
from elasticsearch import Elasticsearch
from rapidfuzz import process, utils

# ==========================================
# CONFIGURATION & PARAMETERS
# ==========================================
ES_HOSTS = ["http://localhost:9200"]
ES_INDEX = "voice_logs_index"
LLM_API_URL = "http://internal-llm-server/v1/chat/completions"
LLM_MODEL_NAME = "inhouse-llm-v1"  # Replace with your local model identifier
LLM_HEADERS = {"Content-Type": "application/json"}

CONTENT_NE_PATH = "content_ne.txt"
PLATFORM_NE_PATH = "platform_ne.txt"
DB_CHECKPOINT_PATH = "pipeline_checkpoint.db"
FINAL_REPORT_PATH = "final_kpi_report.json"

CHUNK_SIZE = 150  # Verbatim extraction uses fewer tokens, safe to batch 150 items
CONCURRENT_REQUESTS = 10  # Max simultaneous API connections to your local LLM server
FUZZY_CLUSTER_CUTOFF = 85.0  # Similarity threshold for grouping unknown variants

# Setup Inhouse Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("pipeline.log"), logging.StreamHandler()],
)


# ==========================================
# PHASE 1: DATABASE & STORAGE INITIALIZATION
# ==========================================
def init_checkpoint_db():
    """Initializes a local SQLite database to persist LLM results per query."""
    conn = sqlite3.connect(DB_CHECKPOINT_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_cache (
            query TEXT PRIMARY KEY,
            content TEXT,
            platform TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def save_to_checkpoint(results: List[Tuple[str, str, str]]):
    """Saves a batch of parsed LLM results safely to the SQLite cache database."""
    conn = sqlite3.connect(DB_CHECKPOINT_PATH)
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR REPLACE INTO llm_cache (query, content, platform) VALUES (?, ?, ?)",
        results,
    )
    conn.commit()
    conn.close()


def load_cached_queries() -> Dict[str, Tuple[str, str]]:
    """Loads all previously processed queries from the SQLite cache to avoid redundant API hits."""
    conn = sqlite3.connect(DB_CHECKPOINT_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT query, content, platform FROM llm_cache")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


# ==========================================
# PHASE 2: DATA INGESTION (ELASTICSEARCH)
# ==========================================
def fetch_top_queries_from_es() -> Dict[str, int]:
    """Fetches unique queries and their search counts from ElasticSearch (Top 65k)."""
    logging.info("Connecting to ElasticSearch to fetch top queries...")
    es = Elasticsearch(ES_HOSTS)

    search_query = {
        "size": 0,
        "aggs": {
            "top_unique_queries": {
                "terms": {"field": "query_string.keyword", "size": 65000}
            }
        },
    }

    try:
        response = es.search(index=ES_INDEX, body=search_query)
        buckets = response["aggregations"]["top_unique_queries"]["buckets"]
        query_map = {b["key"]: b["doc_count"] for b in buckets}
        logging.info(f"Successfully retrieved {len(query_map)} unique queries from ES.")
        return query_map
    except Exception as e:
        logging.error(f"Failed to fetch data from ElasticSearch: {e}")
        raise e


# ==========================================
# PHASE 3: VERBATIM ASYNC LLM EXTRACTION
# ==========================================
async def process_chunk_async(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    chunk: List[str],
) -> List[Tuple[str, str, str]]:
    """Sends queries to the local LLM using strict numeric IDs for flawless mapping back to inputs."""
    
    # Generate the strict tracking barcode list
    prompt_data = [{"id": idx, "text": query} for idx, query in enumerate(chunk)]

    system_prompt = (
        "You are a strict text-segmentation tool. Analyze the provided list of raw voice search queries.\n"
        "For each query, extract the exact substring as-is without changing any spelling, characters, or spacing:\n"
        "1. 'content': The show, movie, music, or sports entity being searched (null if none).\n"
        "2. 'platform': The app or channel name being requested (null if none).\n\n"
        "CRITICAL RULES:\n"
        "- DO NOT normalize names (e.g., if query says 'tarak mehta', output 'tarak mehta').\n"
        "- DO NOT fix typos or change casing.\n"
        "- Return a raw JSON array matching this exact schema: "
        "[{\"id\": numeric_id_from_prompt, \"content\": \"extracted content string or null\", \"platform\": \"extracted platform string or null\"}]. "
        "Do not include markdown wrappers like ```json."
    )

    payload = {
        "model": LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(prompt_data)},
        ],
        "temperature": 0.0,
    }

    async with semaphore:
        for attempt in range(3):
            try:
                async with session.post(LLM_API_URL, headers=LLM_HEADERS, json=payload, timeout=30) as response:
                    if response.status == 200:
                        raw_res = await response.json()
                        content_str = raw_res["choices"][0]["message"]["content"].strip()

                        # Strip markdown blocks if the LLM adds them despite instructions
                        if content_str.startswith("```"):
                            content_str = content_str.strip("```").replace("json", "", 1).strip()

                        parsed_json = json.loads(content_str)

                        # Reconnect the LLM outputs back to original strings using the exact item ID
                        batch_results = []
                        for item in parsed_json:
                            item_id = item.get("id")
                            if isinstance(item_id, int) and 0 <= item_id < len(chunk):
                                original_query = chunk[item_id]
                                batch_results.append((
                                    original_query,
                                    item.get("content"),
                                    item.get("platform")
                                ))
                        return batch_results
                    else:
                        logging.warning(f"LLM API returned status {response.status}. Retrying...")
            except Exception as e:
                logging.error(f"Error during API execution on attempt {attempt}: {e}")
                await asyncio.sleep(1 * (attempt + 1))

        logging.critical(f"Chunk failed entirely after 3 attempts: {chunk[:2]}...")
        return [(q, None, None) for q in chunk]


async def run_llm_extraction(queries_to_process: List[str]):
    """Orchestrates async event loop workers over query chunks."""
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    chunks = [queries_to_process[i : i + CHUNK_SIZE] for i in range(0, len(queries_to_process), CHUNK_SIZE)]

    async with aiohttp.ClientSession() as session:
        tasks = [process_chunk_async(session, semaphore, chunk) for chunk in chunks]
        
        for future in asyncio.as_completed(tasks):
            batch_result = await future
            if batch_result:
                save_to_checkpoint(batch_result)


# ==========================================
# PHASE 4: CLUSTERING & INTELLIGENT REPORTING
# ==========================================
def load_ne_dictionary(file_path: str) -> Set[str]:
    """Loads a named entity list directly into local RAM as a lowercase hash set for O(1) checks."""
    if not os.path.exists(file_path):
        logging.warning(f"Dictionary file not found at {file_path}. Creating blank set.")
        return set()
    with open(file_path, "r", encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


def cluster_unknown_entities(unknown_dict: Dict[str, int], cutoff: float = FUZZY_CLUSTER_CUTOFF) -> List[Dict]:
    """
    Groups unknown entity variants into high-value canonical clusters.
    Sorts by total aggregated count to show true underlying search demand.
    """
    if not unknown_dict:
        return []

    # Sort items by highest count first so the most popular spelling becomes the structural Root
    sorted_items = sorted(unknown_dict.items(), key=lambda x: x[1], reverse=True)
    unique_spellings = [item[0] for item in sorted_items]

    # Deduplicate list using RapidFuzz utility to establish canonical root terms
    canonical_roots = process.dedupe(
        unique_spellings, score_cutoff=cutoff, processor=utils.default_process
    )

    # Initialize buckets for each discovered root
    clusters = {
        root: {"primary_spelling": root, "total_aggregate_count": 0, "spelling_variants": []} 
        for root in canonical_roots
    }

    # Map each minor spelling variant into its closest root group and sum metrics
    for spelling, count in sorted_items:
        match = process.extractOne(
            spelling,
            canonical_roots,
            processor=utils.default_process,
            score_cutoff=cutoff,
        )
        if match:
            root_name = match[0]
            clusters[root_name]["total_aggregate_count"] += count
            if spelling != root_name:
                clusters[root_name]["spelling_variants"].append(spelling)
        else:
            # Fallback for outlier variants that fall outside threshold constraints
            clusters[spelling] = {
                "primary_spelling": spelling, 
                "total_aggregate_count": count, 
                "spelling_variants": []
            }

    # Output structure sorted by the total accumulated count of the entire cluster
    return sorted(list(clusters.values()), key=lambda x: x["total_aggregate_count"], reverse=True)


def generate_metrics_and_insights(
    query_counts: Dict[str, int], cached_llm_data: Dict[str, Tuple[str, str]]
):
    """Processes extraction entries, partitions values against dictionaries, and routes unknown items to the clustering system."""
    logging.info("Loading structural NE dictionaries into local RAM...")
    content_dict = load_ne_dictionary(CONTENT_NE_PATH)
    platform_dict = load_ne_dictionary(PLATFORM_NE_PATH)

    # Temporary maps to accumulate exact raw metrics from raw ES input weights
    aggregated_content: Dict[str, int] = {}
    aggregated_platform: Dict[str, int] = {}

    for query, (content, platform) in cached_llm_data.items():
        weight = query_counts.get(query, 0)

        if content and str(content).strip().lower() != "null":
            cleaned_content = str(content).strip()
            aggregated_content[cleaned_content] = aggregated_content.get(cleaned_content, 0) + weight

        if platform and str(platform).strip().lower() != "null":
            cleaned_platform = str(platform).strip()
            aggregated_platform[cleaned_platform] = aggregated_platform.get(cleaned_platform, 0) + weight

    # Prepare master output document skeleton
    report = {
        "meta": {"total_monitored_unique_queries": len(query_counts)},
        "content_kpis": [],
        "platform_kpis": [],
        "insights_unknown_content": [],
        "insights_unknown_platform": []
    }

    raw_unknown_content = {}
    raw_unknown_platform = {}

    # Evaluate extracted content terms
    for name, count in aggregated_content.items():
        if name.lower() in content_dict:
            report["content_kpis"].append({"name": name, "aggregate_count": count})
        else:
            raw_unknown_content[name] = count

    # Evaluate extracted platform terms
    for name, count in aggregated_platform.items():
        if name.lower() in platform_dict:
            report["platform_kpis"].append({"name": name, "aggregate_count": count})
        else:
            raw_unknown_platform[name] = count

    # Sort standard internal metrics alphabetically or by magnitude safely
    report["content_kpis"].sort(key=lambda x: x["aggregate_count"], reverse=True)
    report["platform_kpis"].sort(key=lambda x: x["aggregate_count"], reverse=True)

    # Compute advanced clustering insights ONLY over missing catalog elements
    logging.info("Clustering raw unknown variances...")
    report["insights_unknown_content"] = cluster_unknown_entities(raw_unknown_content)
    report["insights_unknown_platform"] = cluster_unknown_entities(raw_unknown_platform)

    # Serialize to JSON disk format
    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logging.info(f"Master processing complete. Metrics saved to: {FINAL_REPORT_PATH}")


# ==========================================
# CORE PIPELINE EXECUTION ENGINE
# ==========================================
def main():
    logging.info("Starting Executive Analytics Pipeline...")
    init_checkpoint_db()

    # Step 1: Ingest active analytics statistics from ElasticSearch
    query_counts = fetch_top_queries_from_es()
    if not query_counts:
        logging.error("No data found from ES source. Exiting pipeline.")
        return

    # Step 2: Correlate incoming keys against local persistent cache state
    cache = load_cached_queries()
    missing_queries = [q for q in query_counts.keys() if q not in cache]

    # Step 3: Run asynchronous pipeline workers for completely new searches
    if missing_queries:
        logging.info(f"Found {len(missing_queries)} new queries requiring LLM extraction.")
        asyncio.run(run_llm_extraction(missing_queries))
    else:
        logging.info("All queried phrases successfully fetched from local SQLite state database cache.")

    # Refresh structural view of local memory mapping cache layers
    updated_cache = load_cached_queries()

    # Step 4: Execute local evaluations, clustering configurations, and dump report
    generate_metrics_and_insights(query_counts, updated_cache)


if __name__ == "__main__":
    main()
