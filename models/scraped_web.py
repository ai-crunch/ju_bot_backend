"""
A model for scraped web files.
"""

from pydantic import BaseModel


class ScrapedWebFiles(BaseModel):
    file_path: str
    source_link: str
    source_title: str
