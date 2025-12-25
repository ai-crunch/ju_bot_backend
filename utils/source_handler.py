from typing import Optional, Literal
from urllib.parse import urlparse
from models.qa_messages import SourceMetadata


def enhance_source_metadata(source_data: dict) -> dict:
    """Enhance source metadata for better frontend display"""
    file_path = source_data.get("file_path", "")
    metadata = source_data.get("metadata") or {}

    # Fix potential double 'data/' prefix in file_path
    if file_path.startswith("data/data/"):
        file_path = file_path.replace("data/data/", "data/", 1)

    # Create enhanced metadata
    enhanced_metadata = SourceMetadata()

    # Determine if it's a web source
    parsed_url = urlparse(file_path)
    is_web_source = bool(parsed_url.scheme and parsed_url.netloc)

    if is_web_source:
        # Web source
        enhanced_metadata.is_web_source = True
        enhanced_metadata.source_type = "web"
        enhanced_metadata.source_link = file_path
        enhanced_metadata.clickable = True

        # Try to get title from metadata or create from URL
        if isinstance(metadata, dict) and metadata.get("source_title"):
            enhanced_metadata.source_title = metadata["source_title"]
            enhanced_metadata.display_name = metadata["source_title"]
        else:
            # Create a display name from URL
            domain = parsed_url.netloc
            enhanced_metadata.source_title = f"مصدر من {domain}"
            enhanced_metadata.display_name = f"مصدر من {domain}"
    else:
        # PDF or local file source
        enhanced_metadata.is_web_source = False
        enhanced_metadata.source_type = (
            "pdf" if file_path.lower().endswith(".pdf") else "document"
        )
        enhanced_metadata.clickable = file_path.lower().endswith(".pdf")

        # Extract filename and title
        if isinstance(metadata, dict):
            enhanced_metadata.filename = metadata.get("filename")
            enhanced_metadata.source_title = metadata.get("source_title")

        # Create display name
        if enhanced_metadata.source_title:
            enhanced_metadata.display_name = enhanced_metadata.source_title
        elif enhanced_metadata.filename:
            # Remove extension from filename for display
            display_name = enhanced_metadata.filename
            if "." in display_name:
                display_name = display_name.rsplit(".", 1)[0]
            enhanced_metadata.display_name = display_name
        else:
            enhanced_metadata.display_name = "مستند"

    # Return enhanced source data
    return {
        "text": source_data.get("text", ""),
        "file_path": file_path,
        "metadata": enhanced_metadata,
    }
