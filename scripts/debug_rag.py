"""
RAG ingestion & retrieval diagnostic script.

Usage (run from the ju_bot_backend directory):
    python scripts/debug_rag.py [keyword]

    keyword  — Optional Arabic or English substring to search for in OCR cache
               filenames and Qdrant metadata.  Defaults to "فقه" (Fiqh).

The script checks every layer of the pipeline:
    Layer 1 — OCR cache on disk (ocr_results/)
    Layer 2 — Qdrant point existence (scroll by metadata.file_name)
    Layer 3 — Live retrieval quality (dense + sparse + RRF + reranker)
"""

import sys
import os
import json

# Allow running from the repo root as well
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402 — must come after sys.path fix

config.reload_config()

from utils.vdb import QdrantVDB  # noqa: E402
from qdrant_client.models import Filter, FieldCondition, MatchText  # noqa: E402

KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "فقه"
SEP = "-" * 70


def layer1_ocr_cache(keyword: str) -> None:
    print(SEP)
    print(f"LAYER 1 — OCR Cache  (keyword: '{keyword}')")
    print(SEP)

    ocr_dir = config.OCR.get("results_dir", "ocr_results")
    if not os.path.isdir(ocr_dir):
        print(f"  [ERROR] OCR results directory not found: {ocr_dir}")
        return

    all_files = os.listdir(ocr_dir)
    matched = [f for f in all_files if keyword in f]

    print(f"  Total OCR cache files : {len(all_files)}")
    print(f"  Files matching '{keyword}': {len(matched)}")

    if not matched:
        print("  [WARN] No OCR cache files found for this keyword.")
        print("         Likely causes: upload never completed, OCR failed, or")
        print("         the filename uses different characters than the keyword.")
        return

    for fname in matched[:10]:
        fpath = os.path.join(ocr_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            text = data.get("text", "")
            meta = data.get("metadata", {})
            print(f"\n  File   : {fname}")
            print(f"  Dept   : {meta.get('department_id', 'N/A')}")
            print(f"  Page   : {meta.get('page_number', 'N/A')}")
            print(f"  Words  : {len(text.split())}")
            if len(text.split()) < 10:
                print(f"  [WARN] Very short OCR text — OCR may have failed.")
            print(f"  Preview: {text[:120].strip()!r}")
        except Exception as exc:
            print(f"  [ERROR] Could not read {fname}: {exc}")


def layer2_qdrant_index(keyword: str) -> list:
    print()
    print(SEP)
    print(f"LAYER 2 — Qdrant Index  (keyword: '{keyword}')")
    print(SEP)

    vdb = QdrantVDB()
    client = vdb.client
    collection = config.QDRANT["collection_name"]

    try:
        info = client.get_collection(collection)
        total = info.points_count
        print(f"  Collection         : {collection}")
        print(f"  Total points       : {total}")
    except Exception as exc:
        print(f"  [ERROR] Cannot reach Qdrant: {exc}")
        return []

    # Scroll looking for any point whose metadata.file_name contains the keyword
    try:
        results, _ = client.scroll(
            collection_name=collection,
            limit=50,
            with_payload=True,
            with_vectors=False,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.file_name",
                        match=MatchText(text=keyword),
                    )
                ]
            ),
        )
    except Exception as exc:
        print(f"  [ERROR] Scroll failed: {exc}")
        return []

    print(f"  Points matching '{keyword}': {len(results)}")

    if not results:
        print("  [WARN] No Qdrant points found for this keyword.")
        print("         The file was either never embedded or was deleted.")
        return []

    point_ids = []
    for point in results[:5]:
        payload = point.payload or {}
        meta = payload.get("metadata", {})
        is_active = payload.get("is_active", True)
        text_preview = payload.get("text", "")[:100].strip()
        print(f"\n  Point ID   : {point.id}")
        print(f"  file_path  : {payload.get('file_path', 'N/A')}")
        print(f"  file_name  : {meta.get('file_name', 'N/A')}")
        print(f"  department : {meta.get('department_id', 'N/A')}")
        print(f"  page       : {meta.get('page_number', 'N/A')}")
        print(f"  is_active  : {is_active}")
        if not is_active:
            print("  [WARN] This point is inactive — it will be EXCLUDED from retrieval!")
        print(f"  text preview: {text_preview!r}")
        point_ids.append(point.id)

    return point_ids


def layer3_retrieval(keyword: str) -> None:
    print()
    print(SEP)
    print(f"LAYER 3 — Live Retrieval  (query: '{keyword}')")
    print(SEP)

    vdb = QdrantVDB()
    try:
        results = vdb.retrieve(keyword, limit=10)
    except Exception as exc:
        print(f"  [ERROR] retrieve() raised: {exc}")
        return

    print(f"  Results returned: {len(results)}")

    if not results:
        print("  [WARN] retrieve() returned 0 results.")
        print("         Possible causes: embedder failure, empty collection,")
        print("         or all matching points have is_active=False.")
        return

    for i, r in enumerate(results, 1):
        payload = r.payload or {}
        meta = payload.get("metadata", {})
        text_preview = payload.get("text", "")[:100].strip()
        print(f"\n  [{i}] ID          : {r.id}")
        print(f"       file_name   : {meta.get('file_name', 'N/A')}")
        print(f"       department  : {meta.get('department_id', 'N/A')}")
        print(f"       page        : {meta.get('page_number', 'N/A')}")
        print(f"       is_active   : {payload.get('is_active', True)}")
        print(f"       text preview: {text_preview!r}")

    # Match the keyword against file_name OR the text payload so that documents
    # indexed without a file_name (e.g. via the generator pipeline) are still
    # detected correctly.
    def _point_matches(r) -> bool:
        payload = r.payload or {}
        meta = payload.get("metadata", {})
        if keyword in meta.get("file_name", ""):
            return True
        if keyword in payload.get("file_path", ""):
            return True
        if keyword in payload.get("text", ""):
            return True
        return False

    target_in_results = any(_point_matches(r) for r in results)
    print()
    if target_in_results:
        print("  [OK] Target document WAS found in retrieval results.")
        print("       The agent should be able to answer questions about this document.")
    else:
        print("  [FAIL] Target document was NOT found in retrieval results.")
        print("         Possible causes:")
        print("           - Document not indexed (check Layer 2)")
        print("           - Low similarity score caused by missing E5 prefix (already fixed)")
        print("           - Reranker cut it from top results")


if __name__ == "__main__":
    print(f"\nRAG Debug — keyword: '{KEYWORD}'")
    layer1_ocr_cache(KEYWORD)
    layer2_qdrant_index(KEYWORD)
    layer3_retrieval(KEYWORD)
    print()
    print(SEP)
    print("Done. Check [WARN] and [FAIL] markers above for action items.")
    print(SEP)
