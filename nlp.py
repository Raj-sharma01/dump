import os
import re
from flashtext import KeywordProcessor

# ---------------------------------------------------------
# SIMULATION: Creating your .txt files for testing
# ---------------------------------------------------------
def setup_dummy_text_files():
    with open("platform.txt", "w", encoding="utf-8") as f:
        f.write("netflix\nyoutube\nhbo max\ndisney plus\nhotstar\nprime video\n")
        
    with open("content.txt", "w", encoding="utf-8") as f:
        f.write("moana 2\ntaarak mehta ka ooltah chashmah\ndhoom\navatar\nstranger things\n")

setup_dummy_text_files()


# ---------------------------------------------------------
# LAYER 1: INGESTION & TRIAGE
# ---------------------------------------------------------
def preprocess_and_triage(raw_query: str, country_context: str) -> dict:
    query = raw_query.strip().lower()
    
    # Compress voice-to-text acronym dots: "e. s. p. n." -> "espn"
    acronym_regex = re.compile(r'\b(\w)\s*\.\s*(?=\w\b|\s|$)')
    while "." in query:
        collapsed = acronym_regex.sub(r'\1', query)
        if collapsed == query:
            break
        query = collapsed
        
    # Clean standard trailing punctuation
    query = re.sub(r'[.,\/#!$%\^&\*;:{}=\-_`~()]', ' ', query)
    query = " ".join(query.split())

    # Filter out absolute noise
    if len(query) < 2 or query.isdigit():
        return {
            "status": "UNKNOWN_INTENT",
            "clean_query": query,
            "metadata": {"country": country_context, "reason": "noise_or_too_short"}
        }

    return {
        "status": "PROCEED",
        "clean_query": query,
        "metadata": {"country": country_context}
    }


# ---------------------------------------------------------
# LAYER 2: DYNAMIC FILE-BASED VOCABULARY ENGINE
# ---------------------------------------------------------
class FileBasedVocabularyEngine:
    def __init__(self, platform_file: str, content_file: str):
        self.processor = KeywordProcessor(case_sensitive=False)
        self.load_file_into_trie(platform_file, "PLATFORM")
        self.load_file_into_trie(content_file, "CONTENT")

    def load_file_into_trie(self, file_path: str, entity_type: str):
        """Reads a massive text file line-by-line and stores it efficiently in RAM."""
        if not os.path.exists(file_path):
            print(f"[Error] File not found: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                clean_line = line.strip().lower()
                if clean_line:
                    # FlashText maps the text line to a string token: "CANONICAL_NAME__TYPE"
                    # Example: "netflix" maps to "netflix__PLATFORM"
                    value_string = f"{clean_line}__{entity_type}"
                    self.processor.add_keyword(clean_line, value_string)
                    
        print(f"Successfully loaded {entity_type} data into memory trie structure.")

    def extract_entities(self, triage_result: dict) -> dict:
        query_text = triage_result["clean_query"]
        metadata = triage_result["metadata"]
        
        # FlashText runs an O(n) sweep through the text query
        matches = self.processor.extract_keywords(query_text)
        
        if not matches:
            return {"status": "RESIDUAL", "clean_query": query_text, "extracted_entities": [], "metadata": metadata}
            
        extracted_tuples = []
        for match in matches:
            canonical_name, ent_type = match.split("__", 1)
            extracted_tuples.append((canonical_name, ent_type))
            
        # Determine if the query is a complete match or if leftover unknown words exist
        # Split tokens to check remaining unmatched payload text footprint
        words_in_query = query_text.split()
        matched_words_count = 0
        for name, _ in extracted_tuples:
            matched_words_count += len(name.split())
            
        # If the bulk of the query's words were found in the txt files, it's a Complete Hit
        if matched_words_count >= (len(words_in_query) - 1):
            return {
                "status": "COMPLETE_HIT",
                "extracted_entities": extracted_tuples,
                "confidence": 1.0,
                "metadata": metadata
            }
            
        return {
            "status": "RESIDUAL",
            "clean_query": query_text,
            "extracted_entities": extracted_tuples,
            "metadata": metadata
        }


# ---------------------------------------------------------
# EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    # Initialize engine dynamically using your two text files
    vocab_engine = FileBasedVocabularyEngine("platform.txt", "content.txt")
    
    # Mix of known items from txt files, and completely new unknown entries
    sample_queries = [
        {"query": "watch dhoom", "country": "IN"},            # 'dhoom' is in content.txt
        {"query": "open netflix app", "country": "US"},       # 'netflix' is in platform.txt
        {"query": "watch reelz app", "country": "US"},        # NOT in text files -> Must go to SpaCy
        {"query": "play taarak mehta ka ooltah chashmah on youtube", "country": "IN"} # Both files hit!
    ]
    
    print("\n--- Processing via Text-File-Backed Pipeline ---\n")
    for log in sample_queries:
        triage = preprocess_and_triage(log["query"], log["country"])
        if triage["status"] == "UNKNOWN_INTENT":
            continue
            
        result = vocab_engine.extract_entities(triage)
        
        if result["status"] == "COMPLETE_HIT":
            print(f"✅ [Layer 1 Hit] Query: '{log['query']}' -> Resolved: {result['extracted_entities']}")
        else:
            print(f"🔀 [Layer 1 Miss/Partial] Query: '{log['query']}' -> Sending to Layer 3 (SpaCy) for discovery.")











import spacy
from spacy.pipeline import EntityRuler

class LinguisticParser:
    def __init__(self):
        # 1. Initialize a blank, lightweight English model
        # This is incredibly fast because it only tokenizes the text (chops it into words)
        self.nlp = spacy.blank("en")
        
        # 2. Add the EntityRuler to the pipeline
        self.ruler = self.nlp.add_pipe("entity_ruler")
        self.load_structural_rules()
        
        # 3. Define the suffix words we want to strip out later
        self.suffixes = ["app", "channel", "tv", "station", "hd"]

    def load_structural_rules(self):
        """
        Defines the mathematical shapes of unknown entities. 
        Instead of naming platforms, we describe how they sit in a sentence.
        """
        patterns = [
            # Pattern A: Catch Unknown Platforms based on suffixes
            # Logic: [1 or more alphabetic words] + [A suffix like "app" or "channel"]
            {
                "label": "UNKNOWN_PLATFORM",
                "pattern": [
                    {"IS_ALPHA": True, "OP": "+"},  # The unknown name (e.g., "reelz", "star sports")
                    {"LOWER": {"IN": ["app", "channel", "tv"]}}  # The structural anchor
                ]
            },
            
            # Pattern B: Catch Unknown Content based on action verbs
            # Logic: [Action Verb] + [1 to 4 unknown words]
            {
                "label": "UNKNOWN_CONTENT",
                "pattern": [
                    {"LOWER": {"IN": ["watch", "play", "stream"]}}, # The verb anchor
                    {"IS_ALPHA": True, "OP": "{1,4}"}               # The unknown movie/show
                ]
            }
        ]
        
        # Inject patterns into the spaCy ruler
        self.ruler.add_patterns(patterns)

    def extract_from_misses(self, layer_2_miss_result: dict) -> dict:
        """
        Takes the residual string from Layer 2 and parses it for structural clues.
        """
        query_text = layer_2_miss_result["clean_query"]
        
        # Pass the text through the spaCy pipeline
        doc = self.nlp(query_text)
        
        extracted_entities = []
        
        # Loop through whatever spaCy found based on our rules
        for ent in doc.ents:
            clean_text = ent.text
            
            # Post-processing: If we matched "reelz app", we want to strip "app"
            if ent.label_ == "UNKNOWN_PLATFORM":
                words = clean_text.split()
                if words[-1] in self.suffixes:
                    clean_text = " ".join(words[:-1]) # Keep everything except the last word
            
            # Post-processing: If we matched "watch cool movie", we want to strip "watch"
            elif ent.label_ == "UNKNOWN_CONTENT":
                words = clean_text.split()
                clean_text = " ".join(words[1:]) # Drop the first word (the verb)
                
            extracted_entities.append((clean_text, ent.label_))
            
        # Determine routing status
        if extracted_entities:
            return {
                "status": "DISCOVERY_ROUTED",
                "clean_query": query_text,
                "extracted_entities": extracted_entities,
                "metadata": layer_2_miss_result["metadata"]
            }
            
        # If spaCy found nothing, it's true noise.
        return {
            "status": "NOISE_OR_UNKNOWN_INTENT",
            "clean_query": query_text,
            "metadata": layer_2_miss_result["metadata"]
        }


# ---------------------------------------------------------
# EXECUTION (Simulating a hand-off from Layer 2)
# ---------------------------------------------------------
if __name__ == "__main__":
    parser = LinguisticParser()
    
    # Simulating queries that Layer 2 completely failed to match
    layer_2_misses = [
        {
            "clean_query": "watch reelz app", 
            "metadata": {"country": "US"}
        },
        {
            "clean_query": "play alien romulus", 
            "metadata": {"country": "US"}
        },
        {
            "clean_query": "i am bored show me something", 
            "metadata": {"country": "IN"}
        }
    ]
    
    print("\n--- Processing Layer 2 Misses through Layer 3 (SpaCy) ---\n")
    
    for miss in layer_2_misses:
        result = parser.extract_from_misses(miss)
        
        if result["status"] == "DISCOVERY_ROUTED":
            print(f"✅ [Clue Found] Query: '{miss['clean_query']}'")
            print(f"   -> Extracted: {result['extracted_entities']}")
            print(f"   -> Routing to Layer 4 (Clustering) for group discovery.\n")
        else:
            print(f"❌ [No Clues] Query: '{miss['clean_query']}'")
            print(f"   -> Tagged as NOISE. Routing straight to KPI Dashboard.\n")

















import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import HDBSCAN
from collections import defaultdict

# ---------------------------------------------------------
# LAYER 4: THE ROUTING SWITCH (HARVESTER)
# ---------------------------------------------------------
class Layer4RoutingSwitch:
    def __init__(self):
        # This repository holds items waiting for the end-of-month batch run
        self.oov_content_accumulator = []

    def harvest(self, spacy_result: dict, raw_es_count: int):
        """
        Filters through SpaCy outputs. If an entity is unrecognized,
        it pairs the raw string with its original search volume count.
        """
        if spacy_result["status"] == "DISCOVERY_ROUTED":
            for entity_text, entity_label in spacy_result["extracted_entities"]:
                if entity_label == "UNKNOWN_CONTENT":
                    # Store the string and its search volume weight
                    self.oov_content_accumulator.append({
                        "text": entity_text,
                        "count": raw_es_count,
                        "country": spacy_result["metadata"]["country"]
                    })


# ---------------------------------------------------------
# LAYER 5: THE TWO-TIERED DISCOVERY LOOP (HDBSCAN TANK)
# ---------------------------------------------------------
class OOVDiscoveryEngine:
    def __init__(self, min_cluster_size=2):
        self.min_cluster_size = min_cluster_size
        
        # Define a Character N-Gram Vectorizer (Matches typos based on structural spelling)
        # analyzer='char' breaks "bhajan" into ['bh', 'ha', 'aj', 'ja', 'an']
        self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))

    def process_batch(self, accumulated_data: list):
        if not accumulated_data:
            print("No data accumulated for clustering.")
            return []

        # Deduplicate identical strings but aggregate their counts
        unique_strings_map = defaultdict(int)
        for item in accumulated_data:
            unique_strings_map[item["text"]] += item["count"]

        unique_texts = list(unique_strings_map.keys())
        
        # Step 1: Convert raw string characters into numerical matrices
        X = self.vectorizer.fit_transform(unique_texts)

        # Step 2: Initialize HDBSCAN
        # metric='euclidean' calculates distances across the string matrices
        clusterer = HDBSCAN(min_cluster_size=self.min_cluster_size, metric='euclidean')
        cluster_labels = clusterer.fit_predict(X.toarray())

        # Step 3: Organize items by their discovered clusters
        discovered_clusters = defaultdict(list)
        
        for idx, label in enumerate(cluster_labels):
            text_item = unique_texts[idx]
            total_volume = unique_strings_map[text_item]
            
            # HDBSCAN marks true noise/un-clusterable singletons as -1
            if label == -1:
                cluster_key = "UNCLASSIFIED_INDIVIDUAL_NOISE"
            else:
                cluster_key = f"CLUSTER_{label}"
                
            discovered_clusters[cluster_key].append({
                "phrase": text_item,
                "volume": total_volume
            })

        # Step 4: Refine clusters and find the "Centroid Label" (The most frequent variant)
        final_report = []
        for c_label, items in discovered_clusters.items():
            if c_label == "UNCLASSIFIED_INDIVIDUAL_NOISE":
                continue
                
            # Sort items within the cluster by search volume to find the dominant phrasing
            sorted_items = sorted(items, key=lambda x: x["volume"], reverse=True)
            representative_name = sorted_items[0]["phrase"]
            total_cluster_volume = sum(item["volume"] for item in items)
            
            final_report.append({
                "cluster_id": c_label,
                "assigned_label": representative_name.upper(), # Dominant spelling becomes the catalog signal
                "total_demand_volume": total_cluster_volume,
                "all_variants": [item["phrase"] for item in sorted_items]
            })

        # Sort the final report by total volume so the highest-priority catalog gaps float to the top
        return sorted_items, sorted(final_report, key=lambda x: x["total_demand_volume"], reverse=True)


# ---------------------------------------------------------
# EXECUTION TIMELINE SIMULATION
# ---------------------------------------------------------
if __name__ == "__main__":
    # 1. Initialize our routing switch
    router = Layer4RoutingSwitch()

    # 2. Simulate data extracted from Layer 3 (SpaCy) over the month
    # Notice the massive spelling chaos in these voice searches
    simulated_spacy_outputs = [
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("bhajan", "UNKNOWN_CONTENT")], "metadata": {"country": "IN"}}, 45000),
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("bhajans", "UNKNOWN_CONTENT")], "metadata": {"country": "IN"}}, 12000),
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("morning bhajan", "UNKNOWN_CONTENT")], "metadata": {"country": "IN"}}, 8500),
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("bajan", "UNKNOWN_CONTENT")], "metadata": {"country": "IN"}}, 3200),
        
        # A completely separate content gap cluster appearing in the same month
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("alien romulus", "UNKNOWN_CONTENT")], "metadata": {"country": "US"}}, 90000),
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("alien romlus", "UNKNOWN_CONTENT")], "metadata": {"country": "US"}}, 15000),
        ({"status": "DISCOVERY_ROUTED", "extracted_entities": [("alien romulas", "UNKNOWN_CONTENT")], "metadata": {"country": "US"}}, 4000),
    ]

    # Layer 4 harvests the targets over time
    for spacy_res, count in simulated_spacy_outputs:
        router.harvest(spacy_res, count)

    print(f"--- End of Month Reached ---")
    print(f"Harvested {len(router.oov_content_accumulator)} unmapped search variations from the streaming pipeline.\n")

    # 3. Fire up the Discovery Tank (Layer 5 Batch Process)
    discovery_tank = OOVDiscoveryEngine(min_cluster_size=2)
    _, catalog_gap_report = discovery_tank.process_batch(router.oov_content_accumulator)

    print("--- Discovered Catalog Gap KPI Matrix ---")
    for gap in catalog_gap_report:
        print(f"\n🎯 Discovered Content Trend: '{gap['assigned_label']}'")
        print(f"   💰 Total Aggregated Search Volume: {gap['total_demand_volume']} requests")
        print(f"   📋 Combined Query Variants mapped: {gap['all_variants']}")








import pandas as pd

# ---------------------------------------------------------
# LAYER 6: THE COUNT ROLL-UP ENGINE
# ---------------------------------------------------------
class KPICountRollUpEngine:
    def __init__(self):
        # Master storage matrices for the final dashboard data frames
        self.resolved_traffic = []
        self.catalog_gaps = []
        self.system_noise = []

    def log_known_hit(self, canonical_name, entity_type, volume, country):
        """Captures 100% verified hits from Layer 2 or Layer 3."""
        self.resolved_traffic.append({
            "Entity_Name": canonical_name.upper(),
            "Category": entity_type,
            "Search_Volume": volume,
            "Country": country,
            "Classification": "KNOWN_CATALOG_ITEM"
        })

    def log_discovered_gaps(self, cluster_report, country_default="GLOBAL"):
        """Captures the output of the Layer 5 HDBSCAN tank."""
        for gap in cluster_report:
            self.catalog_gaps.append({
                "Discovered_Trend": gap["assigned_label"],
                "Aggregated_Demand": gap["total_demand_volume"],
                "Variants_Combined": ", ".join(gap["all_variants"]),
                "Primary_Country": country_default
            })

    def log_system_noise(self, clean_query, reason, volume, country):
        """Captures pure garbage, singletons, or empty strings for engine health."""
        self.system_noise.append({
            "Raw_Noise_Phrase": clean_query if clean_query else "[EMPTY_STRING]",
            "Triage_Reason": reason,
            "Impact_Volume": volume,
            "Country": country
        })

    # ---------------------------------------------------------
    # LAYER 7: THE ANALYTICAL KPI STORE (OUTPUT GENERATION)
    # ---------------------------------------------------------
    def compile_dashboard_matrices(self):
        """
        Converts internal memory caches into structured pandas DataFrames.
        In production, these write directly to DuckDB, PostgreSQL, or Parquet files.
        """
        # Matrix 1: Core Platform & Content Volume Share
        df_resolved = pd.DataFrame(self.resolved_traffic)
        if not df_resolved.empty:
            # Group by Name and Category to sum volumes across different countries cleanly
            df_resolved = df_resolved.groupby(["Entity_Name", "Category", "Classification"])["Search_Volume"].sum().reset_index()
            df_resolved = df_resolved.sort_values(by="Search_Volume", ascending=False).reset_index(drop=True)

        # Matrix 2: Catalog Content Gaps (Acquisition Signals)
        df_gaps = pd.DataFrame(self.catalog_gaps)
        if not df_gaps.empty:
            df_gaps = df_gaps.sort_values(by="Aggregated_Demand", ascending=False).reset_index(drop=True)

        # Matrix 3: Voice Engine Health & Structural Noise
        df_noise = pd.DataFrame(self.system_noise)
        if not df_noise.empty:
            df_noise = df_noise.groupby(["Triage_Reason"])["Impact_Volume"].sum().reset_index()
            
        return df_resolved, df_gaps, df_noise


# ---------------------------------------------------------
# END-TO-END PIPELINE SIMULATION (Bringing it all together)
# ---------------------------------------------------------
if __name__ == "__main__":
    # Initialize the final metrics accumulator
    kpi_engine = KPICountRollUpEngine()

    print("--- Simulating Final Pipeline Consolidation ---\n")

    # 1. Simulate Layer 2 & 3 Exact Hits (Fast-pathed directly here)
    kpi_engine.log_known_hit(canonical_name="netflix", entity_type="PLATFORM", volume=89000, country="US")
    kpi_engine.log_known_hit(canonical_name="taarak mehta ka ooltah chashmah", entity_type="CONTENT", volume=150000, country="IN")
    kpi_engine.log_known_hit(canonical_name="youtube", entity_type="PLATFORM", volume=300000, country="GLOBAL")

    # 2. Simulate Layer 1 Garbage/Noise Filters
    kpi_engine.log_system_noise(clean_query="q", reason="too_short_or_numeric", volume=4500, country="IN")
    kpi_engine.log_system_noise(clean_query="889234", reason="too_short_or_numeric", volume=1200, country="US")
    kpi_engine.log_system_noise(clean_query="i am bored show me something", reason="unparseable_linguistic_noise", volume=3500, country="UK")

    # 3. Simulate Layer 5 HDBSCAN Discovery Results
    mock_hdbscan_output = [
        {
            "assigned_label": "BHAJAN",
            "total_demand_volume": 68700,
            "all_variants": ["bhajan", "bhajans", "morning bhajan", "bajan"]
        },
        {
            "assigned_label": "ALIEN ROMULUS",
            "total_demand_volume": 109000,
            "all_variants": ["alien romulus", "alien romlus", "alien romulas"]
        }
    ]
    kpi_engine.log_discovered_gaps(mock_hdbscan_output, country_default="IN")

    # 4. Compile the final dashboard views
    resolved_matrix, gap_matrix, noise_matrix = kpi_engine.compile_dashboard_matrices()

    # --- SHOWCASE THE ANALYTICAL VIEWS ---
    print("==================================================================")
    print("📊 MATRIX 1: PLATFORM & CONTENT VOLUME SHARE (Market Share View)")
    print("==================================================================")
    print(resolved_matrix.to_string(), "\n")

    print("==================================================================")
    print("🎯 MATRIX 2: CATALOG GAP ANALYSIS (What Content You Are Missing)")
    print("==================================================================")
    print(gap_matrix.to_string(), "\n")

    print("==================================================================")
    print("🛠️ MATRIX 3: VOICE SEARCH ENGINE HEALTH (System Degradation View)")
    print("==================================================================")
    print(noise_matrix.to_string())










import json
from openai import OpenAI

class OpenSourceLLMResolver:
    def __init__(self):
        # Point the client to your local/internal Open-Source Model server
        # Default Ollama port: 11434 | Default vLLM port: 8000
        self.client = OpenAI(
            base_url="http://localhost:11434/v1",  # Change to your OSS server URL
            api_key="ollama_or_oss_host"           # Open-source hosts usually don't validate keys
        )
        
        # Specify your local model name (e.g., 'llama3', 'mistral', 'qwen2.5-instruct')
        self.model_name = "llama3" 

    def resolve_cluster_labels(self, cluster_report: list) -> list:
        """
        Sends the rough HDBSCAN clusters to your local open-source model 
        to extract the official entertainment titles.
        """
        payload = []
        for cluster in cluster_report:
            payload.append({
                "temporary_id": cluster["cluster_id"],
                "naive_label": cluster["assigned_label"],
                "all_discovered_variants": cluster["all_variants"]
            })

        system_prompt = (
            "You are a media metadata server. Look at these clusters of messy Smart TV voice "
            "searches and output their official, grammatically correct media titles or platform names. "
            "You must respond ONLY with a raw JSON object matching the exact format shown in the example.\n\n"
            "Example Output Format:\n"
            '{\n  "resolutions": [\n    {"temporary_id": "CLUSTER_0", "official_title": "Clean Title"}\n  ]\n}'
        )
        
        user_prompt = f"Resolve these voice search clusters:\n{json.dumps(payload, indent=2)}"

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                # Enforces structural JSON output if your local engine (like Ollama/vLLM) supports it
                response_format={"type": "json_object"}, 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0  # Keep it completely deterministic
            )
            
            # Read the response text
            raw_content = response.choices[0].message.content
            llm_corrections = json.loads(raw_content)
            
            # Map clean names back into our master cluster report
            corrected_report = []
            corrections_map = {item["temporary_id"]: item["official_title"] for item in llm_corrections["resolutions"]}
            
            for cluster in cluster_report:
                c_id = cluster["cluster_id"]
                cluster["assigned_label"] = corrections_map.get(c_id, cluster["assigned_label"])
                corrected_report.append(cluster)
                
            return corrected_report

        except Exception as e:
            print(f"Local OSS Model call failed: {e}. Falling back to default cluster names.")
            return cluster_report


# ---------------------------------------------------------
# SIMULATION ENGINE
# ---------------------------------------------------------
if __name__ == "__main__":
    # Sample data showing an unpolished HDBSCAN cluster label
    raw_hdbscan_clusters = [
        {
            "cluster_id": "CLUSTER_1",
            "assigned_label": "ALIEN ROMLUS", 
            "total_demand_volume": 109000,
            "all_variants": ["alien romulus", "alien romlus", "alien romulas"]
        }
    ]

    print("--- Testing Open-Source LLM Fallback Connection ---")
    print(f"Targeting local model endpoint via OpenAI Wrapper...")
    
    # Note: This will attempt to connect to your local host. 
    # If no server is running, it will safely hit the 'except' block and retain the original names.
    oss_resolver = OpenSourceLLMResolver()
    processed_report = oss_resolver.resolve_cluster_labels(raw_hdbscan_clusters)
    
    print(f"Result Label: '{processed_report[0]['assigned_label']}'")


