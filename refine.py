import asyncio
import json
import os
import random
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI, RateLimitError, APITimeoutError

AICREDITS_KEY = os.environ.get("AICREDITS_API_KEY", "")

client = AsyncOpenAI(
    base_url="https://api.aicredits.in/v1",
    api_key=AICREDITS_KEY
)

TARGET_MODEL = "google/gemini-2.5-flash-lite"

CONCURRENCY_LIMIT = 5
TARGET_RPM = 55
REQUEST_INTERVAL = 60.0 / TARGET_RPM

RAW_DATA_PATH = "output.json"
OUTPUT_DATA_PATH = "enriched_restaurants.jsonl"
CHECKPOINT_PATH = "processed_ids.txt"

SCHEMA_PROMPT_TEMPLATE = """You are a structured data enrichment engine for restaurant marketing.

Your task is to:
1. Clean and normalize the input JSON
2. Extract meaningful marketing insights from reviews
3. Return ONLY a strict JSON object matching the schema below

IMPORTANT RULES:
- Do NOT use generic words like "good", "nice", "great"
- All insights must be grounded in the reviews
- Infer patterns (not single mentions)
- Be concise and specific
- Do NOT hallucinate missing data. If a field cannot be inferred, use "unknown" or an empty array.

-----------------------------------

OUTPUT SCHEMA:

{
  "brand_identity": {
    "clean_name": "String (remove SEO or location clutter)",
    "cuisine_tags": ["Array of cuisine types"],
    "price_tier": "Affordable | Mid-Range | Premium",
    "ambience_vibes": ["Specific atmosphere traits inferred from reviews"],
    "brand_tone": "e.g. premium elegant / casual friendly / modern vibrant"
  },

  "audience_profile": {
    "target_segments": ["e.g. couples", "families", "corporate dinners", "friends"],
    "occasion_types": ["e.g. date night, celebrations, casual dining"]
  },

  "value_proposition": {
    "top_strengths": [
      "3–5 specific strengths inferred from repeated patterns in reviews"
    ],
    "pain_points": [
      "2–3 real weaknesses or complaints from reviews"
    ]
  },

  "menu_highlights": {
    "highly_rated_dishes": ["Only dishes mentioned positively multiple times"],
    "dishes_to_avoid_featuring": ["Dishes with negative feedback"]
  },

  "operational_metadata": {
    "contact_phone": "String",
    "full_address": "String",
    "has_parking": "yes | no | unknown"
  }
}

-----------------------------------

Return ONLY valid JSON.
No explanations."""

def load_processed_ids() -> set:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def record_checkpoint(business_id: str):
    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as f:
        f.write(f"{business_id}\n")

def save_enriched_record(record_string: str):
    with open(OUTPUT_DATA_PATH, "a", encoding="utf-8") as f:
        f.write(record_string.strip().replace("\n", "") + "\n")

def clean_json_string(raw_str: str) -> str:
    if not raw_str:
        return "{}"

    cleaned = raw_str.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()

async def enrich_object(raw_obj: dict, semaphore: asyncio.Semaphore, processed_ids: set, idx: int):
    business_id = raw_obj.get("business_name") or raw_obj.get("phone") or f"unnamed_record_{idx}"

    if business_id in processed_ids:
        return

    await asyncio.sleep(idx * REQUEST_INTERVAL)

    async with semaphore:
        max_retries = 5
        base_backoff = 2.0

        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=TARGET_MODEL,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    timeout=30.0,
                    messages=[
                        {"role": "system", "content": SCHEMA_PROMPT_TEMPLATE},
                        {"role": "user", "content": f"Raw Data Payload:\n{json.dumps(raw_obj, ensure_ascii=False)}"}
                    ],
                )

                raw_content = response.choices[0].message.content
                sanitized_content = clean_json_string(raw_content)
                parsed_data = json.loads(sanitized_content)

                if "brand_identity" not in parsed_data or "value_proposition" not in parsed_data or "operational_metadata" not in parsed_data:
                    raise ValueError("Model omitted primary mandatory top-level schema blocks.")

                if "clean_name" not in parsed_data["brand_identity"]:
                    raise ValueError("Model failed to parse critical property: brand_identity.clean_name")

                final_safe_string = json.dumps(parsed_data, ensure_ascii=False)

                save_enriched_record(final_safe_string)
                record_checkpoint(business_id)
                print(f"[SUCCESS] Processed record {idx}: {business_id}")

                await asyncio.sleep(REQUEST_INTERVAL)
                return

            except RateLimitError:
                if attempt == max_retries - 1:
                    print(f"[FATAL] Rate limits exhausted for: {business_id}. Skipping.")
                    raise

                wait_time = (base_backoff ** attempt) + random.uniform(0.1, 0.9)
                print(f"[RATE LIMIT 429] Encountered on task {idx}. Retrying in {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)

            except APITimeoutError:
                if attempt == max_retries - 1:
                    print(f"[FATAL] Connection timed out repeatedly for: {business_id}. Skipping.")
                    return

                wait_time = (base_backoff ** attempt) + random.uniform(0.1, 0.9)
                print(f"[TIMEOUT] Task {idx} stalled. Retrying in {wait_time:.1f}s (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)

            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON Decode failed on task {idx}. Reason: {e}")
                print(f"--- RAW CONTENT PREVIEW ---\n{raw_content[:200]}...\n---------------------------")
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[UNKNOWN ERROR] Task {idx} failed due to: {type(e).__name__} - {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

async def main():
    if not os.path.exists(RAW_DATA_PATH):
        print(f"CRITICAL: Input file '{RAW_DATA_PATH}' not found. Please place your raw JSON data here.")
        return

    with open(RAW_DATA_PATH, "r", encoding="utf-8") as f:
        raw_dataset = json.load(f)
        if isinstance(raw_dataset, dict):
            raw_dataset = raw_dataset.get("restaurants", [raw_dataset])

    processed_ids = load_processed_ids()
    print(f"Initializing Ingestion Engine...")
    print(f"-> Found {len(raw_dataset)} total rows in target file.")
    print(f"-> {len(processed_ids)} items resolved historically. Resuming remaining queue...")

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    tasks = [
        enrich_object(item, semaphore, processed_ids, idx)
        for idx, item in enumerate(raw_dataset)
    ]

    await asyncio.gather(*tasks)
    print("\n[COMPLETE] Phase 1 Batch Transformation Pipeline finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())