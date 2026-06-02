from typing import List
from agno.tools import tool
from utils.vdb import QdrantVDB

from qdrant_client.http.models import Record
from utils.vdb import QdrantVDB

qdrant = QdrantVDB()


@tool(
    name="retrieve",
    description="Retrieve sources from the collection based on the query and return the sources",
)
def retrieve(query: str, limit: int = 20) -> List[Record]:
    """
    Retrieve sources from the collection based on the query and return the sources

    Args:
        query: The query to search for
        limit: The maximum number of results to return
    """
    results = qdrant.retrieve(query, limit)
    return results


tools = [
    retrieve,
]
