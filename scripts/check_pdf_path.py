"""
Checks which Unicode normalization form matches the actual file on disk.
Run inside the container: docker exec -it ju_bot_backend python scripts/check_pdf_path.py
"""
import os
import unicodedata

# The path as stored in Qdrant / shown in the settings page
RAW = "data/Schools/School of Shari'a/\u0627\u0644\u062e\u0637\u0637 \u0627\u0644\u062f\u0631\u0627\u0633\u064a\u0629/\u0627\u0644\u0641\u0642\u0647 \u0648\u0623\u0635\u0648\u0644\u0647/\u0627\u0644\u0628\u0643\u0627\u0644\u0648\u0631\u064a\u0648\u0633 \u0641\u064a \u0627\u0644\u0641\u0642\u0647 \u0648\u0623\u0635\u0648\u0644\u0647 2024.pdf"

for form in ("NFC", "NFD", "NFKC", "NFKD"):
    p = unicodedata.normalize(form, RAW)
    print(f"{form}: exists={os.path.exists(p)}")

print("raw:", os.path.exists(RAW))

# List the actual directory to see raw bytes
parent = "data/Schools/School of Shari'a/\u0627\u0644\u062e\u0637\u0637 \u0627\u0644\u062f\u0631\u0627\u0633\u064a\u0629/\u0627\u0644\u0641\u0642\u0647 \u0648\u0623\u0635\u0648\u0644\u0647"
if os.path.isdir(parent):
    for f in os.listdir(parent):
        print("on-disk bytes:", f.encode("utf-8").hex(), "|", f)
else:
    print("Parent dir not found with NFC alef. Trying NFD parent...")
    parent_nfd = unicodedata.normalize("NFD", parent)
    if os.path.isdir(parent_nfd):
        for f in os.listdir(parent_nfd):
            print("on-disk bytes:", f.encode("utf-8").hex(), "|", f)
    else:
        print("Parent dir not found with either form.")
        # Walk data/Schools to find the directory
        for root, dirs, files in os.walk("data/Schools/School of Shari'a"):
            for d in dirs:
                dp = os.path.join(root, d)
                if "\u0641\u0642\u0647" in d:
                    print("Found dir:", dp.encode("utf-8").hex(), "|", dp)
            for fname in files:
                if "\u0641\u0642\u0647" in fname or "\u0628\u0643\u0627" in fname:
                    fp = os.path.join(root, fname)
                    print("Found file:", fname.encode("utf-8").hex()[:60], "|", fp)
