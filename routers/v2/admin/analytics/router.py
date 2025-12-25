from fastapi import APIRouter, Depends, HTTPException, status
from models.database import MongoDB
from routers.v2.admin.dependencies import get_current_admin
from utils.logger import get_logger
from utils.vdb import QdrantVDB
from datetime import datetime, timedelta
import math

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

vdb = QdrantVDB()


@router.get("/summary")
async def get_summary_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns high-level KPI summary for the entire platform.
    """
    try:
        db = MongoDB.get_db()

        # 1. User Stats
        total_users = db["users"].count_documents({})
        admin_users = db["users"].count_documents({"is_admin": True})

        # 2. Chat Stats
        total_chats = db["chats"].count_documents({"is_deleted": {"$ne": True}})

        # 3. Message Stats
        total_messages = db["messages"].count_documents({})
        user_messages = db["messages"].count_documents({"role": "user"})
        assistant_messages = db["messages"].count_documents({"role": "assistant"})

        # 4. Feedback Stats
        feedback_stats = list(
            db["messages"].aggregate(
                [
                    {"$match": {"feedback": {"$exists": True, "$ne": None}}},
                    {
                        "$group": {
                            "_id": None,
                            "thumbs_up": {
                                "$sum": {"$cond": [{"$eq": ["$feedback", 1]}, 1, 0]}
                            },
                            "thumbs_down": {
                                "$sum": {"$cond": [{"$eq": ["$feedback", -1]}, 1, 0]}
                            },
                        }
                    },
                ]
            )
        )

        feedback = (
            feedback_stats[0] if feedback_stats else {"thumbs_up": 0, "thumbs_down": 0}
        )
        total_feedback = feedback["thumbs_up"] + feedback["thumbs_down"]
        feedback_ratio = (
            (feedback["thumbs_up"] / total_feedback * 100) if total_feedback > 0 else 0
        )

        # 5. Token Usage Summary (from agno_sessions)
        token_stats = list(
            db["agno_sessions"].aggregate(
                [
                    {
                        "$group": {
                            "_id": None,
                            "total_input_tokens": {
                                "$sum": "$session_data.session_metrics.input_tokens"
                            },
                            "total_output_tokens": {
                                "$sum": "$session_data.session_metrics.output_tokens"
                            },
                            "total_duration": {
                                "$sum": "$session_data.session_metrics.duration"
                            },
                        }
                    }
                ]
            )
        )
        tokens = (
            token_stats[0]
            if token_stats
            else {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_duration": 0,
            }
        )

        return {
            "users": {
                "total": total_users,
                "admin": admin_users,
                "non_admin": total_users - admin_users,
            },
            "chats": {
                "total": total_chats,
                "avg_per_user": (
                    round(total_chats / total_users, 1) if total_users > 0 else 0
                ),
            },
            "messages": {
                "total": total_messages,
                "user_ratio": (
                    round(user_messages / total_messages * 100, 1)
                    if total_messages > 0
                    else 0
                ),
                "assistant_ratio": (
                    round(assistant_messages / total_messages * 100, 1)
                    if total_messages > 0
                    else 0
                ),
            },
            "feedback": {
                "thumbs_up": feedback["thumbs_up"],
                "thumbs_down": feedback["thumbs_down"],
                "ratio": round(feedback_ratio, 1),
            },
            "performance": {
                "total_tokens": tokens.get("total_input_tokens", 0)
                + tokens.get("total_output_tokens", 0),
                "avg_duration": (
                    round(tokens.get("total_duration", 0) / total_chats, 2)
                    if total_chats > 0
                    else 0
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error fetching summary analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends")
async def get_trends_analytics(days: int = 30, user: dict = Depends(get_current_admin)):
    """
    Returns time-based trends for messages and chats.
    """
    try:
        db = MongoDB.get_db()
        start_date = datetime.utcnow() - timedelta(days=days)

        # Message trends
        message_trends = list(
            db["messages"].aggregate(
                [
                    {"$match": {"timestamp": {"$gte": start_date}}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$timestamp",
                                }
                            },
                            "count": {"$sum": 1},
                            "user_messages": {
                                "$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}
                            },
                            "assistant_messages": {
                                "$sum": {
                                    "$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]
                                }
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )

        # Chat trends
        chat_trends = list(
            db["chats"].aggregate(
                [
                    {
                        "$match": {
                            "created_at": {"$gte": start_date},
                            "is_deleted": {"$ne": True},
                        }
                    },
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$created_at",
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )

        return {"messages": message_trends, "chats": chat_trends}
    except Exception as e:
        logger.error(f"Error fetching trends analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage")
async def get_usage_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns model and provider usage distribution.
    """
    try:
        db = MongoDB.get_db()

        # Model distribution
        model_dist = list(
            db["agno_sessions"].aggregate(
                [
                    {"$group": {"_id": "$agent_data.model.name", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ]
            )
        )

        # Provider distribution
        provider_dist = list(
            db["agno_sessions"].aggregate(
                [
                    {
                        "$group": {
                            "_id": "$agent_data.model.provider",
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1}},
                ]
            )
        )

        return {"models": model_dist, "providers": provider_dist}
    except Exception as e:
        logger.error(f"Error fetching usage analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_performance_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns detailed performance metrics.
    """
    try:
        db = MongoDB.get_db()

        perf_metrics = list(
            db["agno_sessions"].aggregate(
                [
                    {
                        "$group": {
                            "_id": None,
                            "avg_duration": {
                                "$avg": "$session_data.session_metrics.duration"
                            },
                            "min_duration": {
                                "$min": "$session_data.session_metrics.duration"
                            },
                            "max_duration": {
                                "$max": "$session_data.session_metrics.duration"
                            },
                            "avg_input_tokens": {
                                "$avg": "$session_data.session_metrics.input_tokens"
                            },
                            "avg_output_tokens": {
                                "$avg": "$session_data.session_metrics.output_tokens"
                            },
                        }
                    }
                ]
            )
        )

        metrics = perf_metrics[0] if perf_metrics else {}
        if metrics:
            metrics.pop("_id", None)
            # Round values
            for k, v in metrics.items():
                if v is not None:
                    metrics[k] = round(v, 2)

        return metrics
    except Exception as e:
        logger.error(f"Error fetching performance analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/in-depth")
async def get_indepth_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns in-depth analytics from agno_sessions and messages.
    """
    try:
        db = MongoDB.get_db()

        # 1. System Usage Distribution (RAG vs Agent)
        system_dist = list(
            db["messages"].aggregate(
                [
                    {"$match": {"type": {"$exists": True, "$ne": None}}},
                    {"$group": {"_id": "$type", "count": {"$sum": 1}}},
                ]
            )
        )

        # 2. Tool Usage Distribution
        # Each agno_session has multiple runs, each run has multiple tools
        tool_stats = list(
            db["agno_sessions"].aggregate(
                [
                    {"$unwind": "$runs"},
                    {"$unwind": "$runs.tools"},
                    {
                        "$group": {
                            "_id": "$runs.tools.tool_name",
                            "count": {"$sum": 1},
                            "error_count": {
                                "$sum": {"$cond": ["$runs.tools.tool_call_error", 1, 0]}
                            },
                        }
                    },
                    {"$sort": {"count": -1}},
                ]
            )
        )

        # 3. Reference/Source Analytics
        source_stats = list(
            db["agno_sessions"].aggregate(
                [
                    {"$unwind": "$runs"},
                    {
                        "$project": {
                            "sources_count": {
                                "$size": {"$ifNull": ["$runs.content.sources", []]}
                            },
                            "sources": {"$ifNull": ["$runs.content.sources", []]},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "avg_references": {"$avg": "$sources_count"},
                            "total_references": {"$sum": "$sources_count"},
                            "all_source_ids": {"$push": "$sources"},
                        }
                    },
                ]
            )
        )

        # Flatten all_source_ids and count occurrences for most referenced sources
        # This is a bit complex in aggregation, might be easier to do some processing here
        # But let's try a better aggregation for most referenced sources
        most_referenced = list(
            db["agno_sessions"].aggregate(
                [
                    {"$unwind": "$runs"},
                    {
                        "$unwind": {
                            "path": "$runs.content.sources",
                            "preserveNullAndEmptyArrays": False,
                        }
                    },
                    {"$group": {"_id": "$runs.content.sources", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 10},
                ]
            )
        )

        # 4. Agent Statistics
        agent_stats = list(
            db["agno_sessions"].aggregate(
                [
                    {
                        "$project": {
                            "num_runs": {"$size": {"$ifNull": ["$runs", []]}},
                            "num_tools": {
                                "$sum": {
                                    "$map": {
                                        "input": {"$ifNull": ["$runs", []]},
                                        "as": "run",
                                        "in": {
                                            "$size": {"$ifNull": ["$$run.tools", []]}
                                        },
                                    }
                                }
                            },
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "avg_runs_per_session": {"$avg": "$num_runs"},
                            "avg_tools_per_session": {"$avg": "$num_tools"},
                            "total_tool_calls": {"$sum": "$num_tools"},
                        }
                    },
                ]
            )
        )

        # Format and round results
        sources = (
            source_stats[0]
            if source_stats
            else {"avg_references": 0, "total_references": 0}
        )
        agents = (
            agent_stats[0]
            if agent_stats
            else {
                "avg_runs_per_session": 0,
                "avg_tools_per_session": 0,
                "total_tool_calls": 0,
            }
        )

        return {
            "systems": system_dist,
            "tools": tool_stats,
            "references": {
                "avg_per_run": round(sources.get("avg_references", 0), 2),
                "total": sources.get("total_references", 0),
                "most_referenced": most_referenced,
            },
            "agent_metrics": {
                "avg_runs_per_session": round(agents.get("avg_runs_per_session", 0), 2),
                "avg_tools_per_session": round(
                    agents.get("avg_tools_per_session", 0), 2
                ),
                "total_tool_calls": agents.get("total_tool_calls", 0),
            },
        }
    except Exception as e:
        logger.error(f"Error fetching in-depth analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/source/{source_id}")
async def get_source_info(source_id: str, user: dict = Depends(get_current_admin)):
    """
    Retrieves detailed information from Qdrant for a specific source ID.
    """
    try:
        # Convert source_id to int if possible, Qdrant IDs can be int or UUID
        try:
            sid = int(source_id)
        except ValueError:
            sid = source_id

        results = vdb.get_sources([sid])
        if not results:
            raise HTTPException(status_code=404, detail="Source not found in Qdrant")

        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching source info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources")
async def get_resource_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns analytics about the resources (documents vs web).
    """
    try:
        db = MongoDB.get_db()

        # 1. Count citations per source ID from MongoDB
        citation_counts = list(
            db["agno_sessions"].aggregate(
                [
                    {"$unwind": "$runs"},
                    {
                        "$unwind": {
                            "path": "$runs.content.sources",
                            "preserveNullAndEmptyArrays": False,
                        }
                    },
                    {"$group": {"_id": "$runs.content.sources", "count": {"$sum": 1}}},
                ]
            )
        )

        if not citation_counts:
            return {"documents": [], "web": []}

        # 2. Map IDs to resource names/paths using Qdrant
        source_ids = [c["_id"] for c in citation_counts]
        # Qdrant retrieve limit is usually fine for a reasonable number of IDs
        # If we have thousands, we might need to batch this
        qdrant_info = vdb.get_sources(source_ids)

        id_to_resource = {}
        for record in qdrant_info:
            payload = record.payload or {}
            metadata = payload.get("metadata", {})
            file_path = payload.get("file_path", "Unknown")
            is_web = metadata.get("is_web_source", False) or file_path.startswith(
                "http"
            )

            # Normalize path: remove redundant data/ prefix if it exists for document links
            normalized_path = file_path
            if not is_web and normalized_path.startswith("data/data/"):
                normalized_path = normalized_path.replace("data/data/", "data/", 1)

            title = (
                metadata.get("source_title") or metadata.get("file_name") or file_path
            )

            id_to_resource[record.id] = {
                "title": title,
                "path": normalized_path,
                "is_web": is_web,
            }

        # 3. Group citations by resource
        resource_stats = {}
        for citation in citation_counts:
            sid = citation["_id"]
            info = id_to_resource.get(sid)
            if not info:
                continue

            path = info["path"]
            if path not in resource_stats:
                resource_stats[path] = {
                    "title": info["title"],
                    "is_web": info["is_web"],
                    "citations": 0,
                    "unique_chunks_cited": 0,
                }

            resource_stats[path]["citations"] += citation["count"]
            resource_stats[path]["unique_chunks_cited"] += 1

        # 4. Separate into documents and web
        docs = []
        web = []
        for path, stats in resource_stats.items():
            if stats["is_web"]:
                web.append({**stats, "path": path})
            else:
                docs.append({**stats, "path": path})

        return {
            "documents": sorted(docs, key=lambda x: x["citations"], reverse=True),
            "web": sorted(web, key=lambda x: x["citations"], reverse=True),
        }
    except Exception as e:
        logger.error(f"Error fetching resource analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
