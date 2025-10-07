import os
import json
from tqdm import tqdm
from pathlib import Path

from utils.vdb import QdrantVDB
import config

def extract_metadata_from_path(file_path, base_path):
    """Extract metadata from file path structure"""
    # Convert to Path objects for easier manipulation
    file_path = Path(file_path)
    base_path = Path(base_path)
    
    # Get relative path from base directory
    relative_path = file_path.relative_to(base_path)
    
    # Extract folder hierarchy
    folders = list(relative_path.parts[:-1])  # All parts except filename
    filename = relative_path.name
    
    # Create metadata dictionary
    metadata = {
        "filename": filename,
        "path": str(file_path)
    }
    
    # Add folder hierarchy to metadata
    for i, folder in enumerate(folders):
        if i == 0:
            # First level folder
            metadata[folder.lower().replace(" ", "_")] = folders[i+1] if i+1 < len(folders) else filename.replace(".pdf", "")
        else:
            # Subsequent folders
            prev_folder = folders[i-1].lower().replace(" ", "_")
            current_folder = folder.lower().replace(" ", "_")
            metadata[current_folder] = folders[i+1] if i+1 < len(folders) else filename.replace(".pdf", "")
    
    return metadata


def process_json_chunks(json_file_path: str, source_link: str, source_title: str):
    """
    Process pre-chunked JSON data and embed it.
    
    Args:
        json_file_path: Path to the JSON file containing chunks
        source_link: URL source of the content
        source_title: Title for the source
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"Loaded {len(chunks)} chunks from JSON file")
        return chunks, source_link, source_title
        
    except Exception as e:
        print(f"Error processing JSON file {json_file_path}: {str(e)}")
        return None, None, None


if __name__ == "__main__":
    qdrant_vdb = QdrantVDB()
    data_path = config.DATA_DIR_PATH
    
    # Process JSON file with legal affairs data
    json_file_path = os.path.join(data_path, "meaningful_chunks_with_metadata.json")
    if os.path.exists(json_file_path):
        print("Processing JSON file with pre-chunked data...")
        chunks, source_link, source_title = process_json_chunks(
            json_file_path, 
            "https://units.ju.edu.jo/ar/LegalAffairs/Regulations.aspx",
            "دائرة الشؤون القانونية - الأنظمة والتعليمات"
        )
        
        if chunks:
            try:
                qdrant_vdb.embed_json_chunks(chunks, source_link, source_title)
                print(f"Successfully embedded {len(chunks)} chunks from JSON file")
            except Exception as e:
                print(f"Error embedding JSON chunks: {str(e)}")
        print("-" * 50)
    else:
        print(f"JSON file not found at: {json_file_path}")
    
    # Process PDF files
    pdf_files = []
    for root, dirs, files in os.walk(data_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                file_path = os.path.join(root, file)
                pdf_files.append(file_path)

    print(f"Found {len(pdf_files)} PDF files")

    # Iterate through all PDF files with progress bar
    for file_path in tqdm(pdf_files, desc="Processing PDF files"):
        print(f"Processing: {file_path}")
        metadata = extract_metadata_from_path(file_path, data_path)
        # Add source info for PDF files
        metadata.update({
            'source_title': os.path.basename(file_path).replace('.pdf', ''),
            'is_web_source': False
        })
        print(f"Metadata: {metadata}")
        
        try:
            qdrant_vdb.embed_file(file_path, metadata)
            print(f"Successfully embedded: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Error embedding {os.path.basename(file_path)}: {str(e)}")

        print("-" * 50)
