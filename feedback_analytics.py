#!/usr/bin/env python3
"""
JU Bot Feedback Analytics Script

This script connects to MongoDB and provides comprehensive analysis of feedback data
including statistics, trends, and insights for improving the chatbot service.

Usage:
    python feedback_analytics.py [--export] [--format json|csv]
"""

import argparse
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pymongo import MongoClient
from collections import defaultdict, Counter
import sys
import os

# Add the current directory to Python path to import config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config


class FeedbackAnalytics:
    def __init__(self):
        """Initialize MongoDB connection"""
        try:
            self.client = self._get_mongodb_client()
            mongo_config = config.MONGODB
            self.db = self.client[mongo_config["database"]]
            self.collection = self.db[mongo_config["collection"]]

            # Test connection
            self.client.admin.command("ping")
            print("✅ Successfully connected to MongoDB")

        except Exception as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            sys.exit(1)

    def _get_mongodb_client(self):
        """Get MongoDB client connection with fallback authentication"""
        mongo_config = config.MONGODB

        print(
            f"🔍 Attempting to connect to MongoDB at {mongo_config['host']}:{mongo_config['port']}"
        )
        print(f"📊 Using database: {mongo_config['database']}")
        print(f"👤 Username from config: {mongo_config['username']}")

        # Try authenticated connection with configured credentials first
        try:
            auth_connection = f"mongodb://{mongo_config['username']}:{mongo_config['password']}@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
            client = MongoClient(auth_connection)
            client.admin.command("ping")

            # Test database operations
            db = client[mongo_config["database"]]
            collection = db[mongo_config["collection"]]
            collection.count_documents({})

            print("🔐 Connected to MongoDB with configured credentials")
            return client

        except Exception as auth_error:
            print(f"⚠️ Configured credentials failed: {auth_error}")

            # Fallback to admin user (which we know exists)
            try:
                admin_connection = f"mongodb://admin:password@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
                client = MongoClient(admin_connection)
                client.admin.command("ping")

                # Test database operations
                db = client[mongo_config["database"]]
                collection = db[mongo_config["collection"]]
                collection.count_documents({})

                print("🔐 Connected to MongoDB with admin credentials")
                return client

            except Exception as admin_error:
                print(f"⚠️ Admin credentials failed: {admin_error}")

                # Final fallback to connection without authentication
                try:
                    simple_connection = (
                        f"mongodb://{mongo_config['host']}:{mongo_config['port']}"
                    )
                    client = MongoClient(simple_connection)
                    client.admin.command("ping")

                    # Test database operations
                    db = client[mongo_config["database"]]
                    collection = db[mongo_config["collection"]]
                    collection.count_documents({})

                    print("🔓 Connected to MongoDB without authentication")
                    return client

                except Exception as simple_error:
                    print(f"❌ All authentication methods failed:")
                    print(f"   - Configured auth: {auth_error}")
                    print(f"   - Admin auth: {admin_error}")
                    print(f"   - No auth: {simple_error}")
                    raise Exception(f"Could not connect to MongoDB with any method")

    def get_basic_stats(self) -> Dict[str, Any]:
        """Get basic feedback statistics"""
        print("📊 Calculating basic statistics...")

        total_feedback = self.collection.count_documents({})
        thumbs_up = self.collection.count_documents({"feedback_type": "thumbs_up"})
        thumbs_down = self.collection.count_documents({"feedback_type": "thumbs_down"})
        general_feedback = self.collection.count_documents(
            {"feedback_type": "feedback"}
        )

        # Calculate percentages
        thumbs_up_pct = (thumbs_up / total_feedback * 100) if total_feedback > 0 else 0
        thumbs_down_pct = (
            (thumbs_down / total_feedback * 100) if total_feedback > 0 else 0
        )
        general_feedback_pct = (
            (general_feedback / total_feedback * 100) if total_feedback > 0 else 0
        )

        # Satisfaction rate (thumbs up / (thumbs up + thumbs down))
        total_ratings = thumbs_up + thumbs_down
        satisfaction_rate = (
            (thumbs_up / total_ratings * 100) if total_ratings > 0 else 0
        )

        return {
            "total_feedback": total_feedback,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "general_feedback": general_feedback,
            "thumbs_up_percentage": round(thumbs_up_pct, 2),
            "thumbs_down_percentage": round(thumbs_down_pct, 2),
            "general_feedback_percentage": round(general_feedback_pct, 2),
            "satisfaction_rate": round(satisfaction_rate, 2),
        }

    def get_temporal_analysis(self) -> Dict[str, Any]:
        """Analyze feedback trends over time"""
        print("📈 Analyzing temporal trends...")

        # Get feedback from last 30 days
        thirty_days_ago = datetime.now().replace(tzinfo=None) - timedelta(days=30)

        pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {
                "$group": {
                    "_id": {
                        "date": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$timestamp",
                            }
                        },
                        "type": "$feedback_type",
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.date": 1}},
        ]

        results = list(self.collection.aggregate(pipeline))

        # Organize data by date
        daily_stats = defaultdict(
            lambda: {"thumbs_up": 0, "thumbs_down": 0, "feedback": 0}
        )

        for result in results:
            date = result["_id"]["date"]
            feedback_type = result["_id"]["type"]
            count = result["count"]
            daily_stats[date][feedback_type] = count

        return dict(daily_stats)

    def get_agent_performance(self) -> Dict[str, Any]:
        """Compare performance between agent and simple chat"""
        print("🤖 Analyzing agent vs simple chat performance...")

        agent_stats = self.collection.aggregate(
            [
                {
                    "$group": {
                        "_id": "$agent_used",
                        "total": {"$sum": 1},
                        "thumbs_up": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$feedback_type", "thumbs_up"]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "thumbs_down": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$feedback_type", "thumbs_down"]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "feedback": {
                            "$sum": {
                                "$cond": [{"$eq": ["$feedback_type", "feedback"]}, 1, 0]
                            }
                        },
                    }
                }
            ]
        )

        results = {}
        for stat in agent_stats:
            agent_used = "agent" if stat["_id"] else "simple"
            total_ratings = stat["thumbs_up"] + stat["thumbs_down"]
            satisfaction = (
                (stat["thumbs_up"] / total_ratings * 100) if total_ratings > 0 else 0
            )

            results[agent_used] = {
                "total_feedback": stat["total"],
                "thumbs_up": stat["thumbs_up"],
                "thumbs_down": stat["thumbs_down"],
                "general_feedback": stat["feedback"],
                "satisfaction_rate": round(satisfaction, 2),
            }

        return results

    def get_feedback_messages_analysis(self) -> Dict[str, Any]:
        """Analyze detailed feedback messages"""
        print("💬 Analyzing feedback messages...")

        # Get all feedback with messages
        feedback_with_messages = list(
            self.collection.find(
                {"feedback_message": {"$exists": True, "$ne": None, "$ne": ""}},
                {
                    "feedback_type": 1,
                    "feedback_message": 1,
                    "timestamp": 1,
                    "agent_used": 1,
                },
            ).sort("timestamp", -1)
        )

        # Categorize by type
        categorized = {"thumbs_down": [], "feedback": []}

        for feedback in feedback_with_messages:
            if feedback["feedback_type"] in categorized:
                categorized[feedback["feedback_type"]].append(
                    {
                        "message": feedback["feedback_message"],
                        "timestamp": (
                            feedback["timestamp"].isoformat()
                            if feedback.get("timestamp")
                            else None
                        ),
                        "agent_used": feedback.get("agent_used", False),
                    }
                )

        # Get common keywords/themes
        all_messages = [f["feedback_message"] for f in feedback_with_messages]
        word_frequency = Counter()

        for message in all_messages:
            if message:  # Check if message is not None or empty
                # Simple word extraction (you could enhance this with NLP)
                words = message.lower().split()
                # Filter out common words
                filtered_words = [
                    w
                    for w in words
                    if len(w) > 3
                    and w
                    not in [
                        "that",
                        "this",
                        "with",
                        "from",
                        "they",
                        "were",
                        "been",
                        "have",
                        "their",
                    ]
                ]
                word_frequency.update(filtered_words)

        return {
            "total_messages": len(feedback_with_messages),
            "by_type": {k: len(v) for k, v in categorized.items()},
            "recent_messages": {
                "thumbs_down": categorized["thumbs_down"][:10],
                "feedback": categorized["feedback"][:10],
            },
            "common_keywords": dict(word_frequency.most_common(20)),
        }

    def get_session_analysis(self) -> Dict[str, Any]:
        """Analyze feedback by session"""
        print("🔍 Analyzing session patterns...")

        session_stats = self.collection.aggregate(
            [
                {
                    "$group": {
                        "_id": "$session_id",
                        "feedback_count": {"$sum": 1},
                        "types": {"$push": "$feedback_type"},
                        "agent_used": {"$first": "$agent_used"},
                        "first_feedback": {"$min": "$timestamp"},
                        "last_feedback": {"$max": "$timestamp"},
                    }
                },
                {
                    "$project": {
                        "feedback_count": 1,
                        "agent_used": 1,
                        "first_feedback": 1,
                        "last_feedback": 1,
                        "has_thumbs_up": {"$in": ["thumbs_up", "$types"]},
                        "has_thumbs_down": {"$in": ["thumbs_down", "$types"]},
                        "has_feedback": {"$in": ["feedback", "$types"]},
                    }
                },
            ]
        )

        sessions = list(session_stats)

        return {
            "total_sessions": len(sessions),
            "avg_feedback_per_session": (
                round(sum(s["feedback_count"] for s in sessions) / len(sessions), 2)
                if sessions
                else 0
            ),
            "sessions_with_positive_only": len(
                [
                    s
                    for s in sessions
                    if s.get("has_thumbs_up") and not s.get("has_thumbs_down")
                ]
            ),
            "sessions_with_negative_only": len(
                [
                    s
                    for s in sessions
                    if s.get("has_thumbs_down") and not s.get("has_thumbs_up")
                ]
            ),
            "sessions_with_mixed_feedback": len(
                [
                    s
                    for s in sessions
                    if s.get("has_thumbs_up") and s.get("has_thumbs_down")
                ]
            ),
            "sessions_with_detailed_feedback": len(
                [s for s in sessions if s.get("has_feedback")]
            ),
        }

    def generate_insights(self, stats: Dict[str, Any]) -> List[str]:
        """Generate actionable insights from the data"""
        insights = []

        basic = stats["basic_stats"]
        agent_perf = stats.get("agent_performance", {})
        messages = stats["feedback_messages"]

        # Satisfaction insights
        if basic["satisfaction_rate"] >= 80:
            insights.append(
                f"🎉 Excellent satisfaction rate of {basic['satisfaction_rate']}%!"
            )
        elif basic["satisfaction_rate"] >= 60:
            insights.append(
                f"👍 Good satisfaction rate of {basic['satisfaction_rate']}%, but there's room for improvement."
            )
        else:
            insights.append(
                f"⚠️ Low satisfaction rate of {basic['satisfaction_rate']}% needs immediate attention."
            )

        # Agent vs Simple comparison
        if agent_perf:
            agent_sat = agent_perf.get("agent", {}).get("satisfaction_rate", 0)
            simple_sat = agent_perf.get("simple", {}).get("satisfaction_rate", 0)

            if agent_sat > simple_sat:
                insights.append(
                    f"🤖 Agent mode performs better ({agent_sat}%) than simple mode ({simple_sat}%)"
                )
            elif simple_sat > agent_sat:
                insights.append(
                    f"💡 Simple mode performs better ({simple_sat}%) than agent mode ({agent_sat}%)"
                )

        # Feedback volume insights
        if basic["total_feedback"] < 10:
            insights.append(
                "📈 Consider encouraging more user feedback to get better insights."
            )

        # Detailed feedback insights
        if messages["total_messages"] > 0:
            insights.append(
                f"💬 {messages['total_messages']} users provided detailed feedback - valuable for improvements!"
            )

            if messages["common_keywords"]:
                top_keywords = list(messages["common_keywords"].keys())[:3]
                insights.append(f"🔍 Most mentioned topics: {', '.join(top_keywords)}")

        return insights

    def get_feedback_table_data(self) -> List[Dict[str, Any]]:
        """Get all feedback data for table display"""
        print("📋 Fetching feedback table data...")

        feedback_data = list(
            self.collection.find(
                {},
                {
                    "question": 1,
                    "answer": 1,
                    "feedback_type": 1,
                    "feedback_message": 1,
                    "agent_used": 1,
                    "timestamp": 1,
                    "session_id": 1,
                    "message_id": 1,
                },
            ).sort("timestamp", -1)
        )

        return feedback_data

    def print_feedback_table(self, limit: int = 20):
        """Print feedback data in a table format"""
        feedback_data = self.get_feedback_table_data()

        if not feedback_data:
            print("📋 No feedback data available")
            return

        print(f"\n📋 FEEDBACK TABLE (Latest {min(limit, len(feedback_data))} entries)")
        print("=" * 150)

        # Table headers
        headers = ["Date", "Type", "Question", "Answer", "Feedback", "Agent", "Session"]
        col_widths = [12, 8, 30, 40, 25, 6, 12]

        # Print header
        header_line = "|".join(
            f" {header:<{width-1}}" for header, width in zip(headers, col_widths)
        )
        print(header_line)
        print("-" * 150)

        # Print data rows
        for i, feedback in enumerate(feedback_data[:limit]):
            # Format data
            date_str = (
                feedback.get("timestamp", datetime.now()).strftime("%Y-%m-%d")
                if feedback.get("timestamp")
                else "Unknown"
            )

            feedback_type = feedback.get("feedback_type", "")
            type_emoji = {"thumbs_up": "👍", "thumbs_down": "👎", "feedback": "💬"}.get(
                feedback_type, ""
            )
            type_str = f"{type_emoji} {feedback_type}"

            question = (
                feedback.get("question", "")[:28] + "..."
                if len(feedback.get("question", "")) > 28
                else feedback.get("question", "")
            )

            answer = (
                feedback.get("answer", "")[:38] + "..."
                if len(feedback.get("answer", "")) > 38
                else feedback.get("answer", "")
            )

            feedback_msg = feedback.get("feedback_message", "")
            if feedback_msg:
                feedback_msg = (
                    feedback_msg[:23] + "..."
                    if len(feedback_msg) > 23
                    else feedback_msg
                )
            else:
                feedback_msg = "-"

            agent_str = "Yes" if feedback.get("agent_used", False) else "No"

            session_id = feedback.get("session_id", "")
            if session_id and len(session_id) > 10:
                session_id = session_id[-10:]  # Show last 10 chars
            elif not session_id:
                session_id = "-"

            # Print row
            row_data = [
                date_str,
                type_str,
                question,
                answer,
                feedback_msg,
                agent_str,
                session_id,
            ]
            row_line = "|".join(
                f" {str(data):<{width-1}}" for data, width in zip(row_data, col_widths)
            )
            print(row_line)

        print("=" * 150)
        print(
            f"📊 Showing {min(limit, len(feedback_data))} of {len(feedback_data)} total feedback entries"
        )
        print()

    def print_report(self, stats: Dict[str, Any], table_limit: int = 10):
        """Print a comprehensive report"""
        print("\n" + "=" * 80)
        print("🎯 JU BOT FEEDBACK ANALYTICS REPORT")
        print("=" * 80)
        print(f"📅 Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Basic Statistics
        basic = stats["basic_stats"]
        print("📊 BASIC STATISTICS")
        print("-" * 40)
        print(f"Total Feedback Entries: {basic['total_feedback']}")
        print(f"👍 Thumbs Up: {basic['thumbs_up']} ({basic['thumbs_up_percentage']}%)")
        print(
            f"👎 Thumbs Down: {basic['thumbs_down']} ({basic['thumbs_down_percentage']}%)"
        )
        print(
            f"💬 General Feedback: {basic['general_feedback']} ({basic['general_feedback_percentage']}%)"
        )
        print(f"😊 Satisfaction Rate: {basic['satisfaction_rate']}%")
        print()

        # Agent Performance
        if "agent_performance" in stats:
            print("🤖 AGENT vs SIMPLE CHAT PERFORMANCE")
            print("-" * 40)
            for mode, data in stats["agent_performance"].items():
                print(f"{mode.upper()} MODE:")
                print(f"  Total Feedback: {data['total_feedback']}")
                print(f"  Satisfaction Rate: {data['satisfaction_rate']}%")
                print(
                    f"  👍 {data['thumbs_up']} | 👎 {data['thumbs_down']} | 💬 {data['general_feedback']}"
                )
                print()

        # Feedback Messages Analysis
        messages = stats["feedback_messages"]
        print("💬 DETAILED FEEDBACK ANALYSIS")
        print("-" * 40)
        print(f"Total Messages: {messages['total_messages']}")
        print(
            f"Improvement Suggestions (👎): {messages['by_type'].get('thumbs_down', 0)}"
        )
        print(f"General Feedback (💬): {messages['by_type'].get('feedback', 0)}")
        print()

        if messages["common_keywords"]:
            print("🔍 MOST MENTIONED KEYWORDS:")
            for keyword, count in list(messages["common_keywords"].items())[:10]:
                print(f"  {keyword}: {count} times")
            print()

        # Session Analysis
        if "session_analysis" in stats:
            session = stats["session_analysis"]
            print("🔍 SESSION ANALYSIS")
            print("-" * 40)
            print(f"Total Sessions: {session['total_sessions']}")
            print(f"Avg Feedback per Session: {session['avg_feedback_per_session']}")
            print(f"Positive-only Sessions: {session['sessions_with_positive_only']}")
            print(f"Negative-only Sessions: {session['sessions_with_negative_only']}")
            print(f"Mixed Feedback Sessions: {session['sessions_with_mixed_feedback']}")
            print()

        # Recent Feedback Messages
        if messages["recent_messages"]["thumbs_down"]:
            print("⚠️ RECENT IMPROVEMENT SUGGESTIONS:")
            print("-" * 40)
            for i, msg in enumerate(messages["recent_messages"]["thumbs_down"][:5], 1):
                timestamp = msg["timestamp"][:10] if msg["timestamp"] else "Unknown"
                agent_mode = "Agent" if msg["agent_used"] else "Simple"
                print(f"{i}. [{timestamp}] [{agent_mode}] {msg['message'][:100]}...")
            print()

        # Insights
        insights = stats["insights"]
        print("💡 KEY INSIGHTS & RECOMMENDATIONS")
        print("-" * 40)
        for i, insight in enumerate(insights, 1):
            print(f"{i}. {insight}")
        print()

        print("=" * 80)

        # Print feedback table
        self.print_feedback_table(limit=table_limit)

    def export_data(
        self, stats: Dict[str, Any], format_type: str = "json", filename: str = None
    ):
        """Export data to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ju_bot_feedback_analytics_{timestamp}.{format_type}"

        if format_type == "json":
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, ensure_ascii=False, default=str)

        elif format_type == "csv":
            # Export basic stats to CSV
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Basic stats
                writer.writerow(["Metric", "Value"])
                basic = stats["basic_stats"]
                writer.writerow(["Total Feedback", basic["total_feedback"]])
                writer.writerow(["Thumbs Up", basic["thumbs_up"]])
                writer.writerow(["Thumbs Down", basic["thumbs_down"]])
                writer.writerow(["General Feedback", basic["general_feedback"]])
                writer.writerow(["Satisfaction Rate (%)", basic["satisfaction_rate"]])

                # Agent performance
                if "agent_performance" in stats:
                    writer.writerow([])
                    writer.writerow(["Agent Performance"])
                    writer.writerow(
                        [
                            "Mode",
                            "Total",
                            "Thumbs Up",
                            "Thumbs Down",
                            "Satisfaction Rate",
                        ]
                    )
                    for mode, data in stats["agent_performance"].items():
                        writer.writerow(
                            [
                                mode,
                                data["total_feedback"],
                                data["thumbs_up"],
                                data["thumbs_down"],
                                data["satisfaction_rate"],
                            ]
                        )

        print(f"📁 Data exported to: {filename}")

    def run_analysis(
        self, export: bool = False, export_format: str = "json", table_limit: int = 10
    ):
        """Run complete analysis"""
        print("🚀 Starting JU Bot Feedback Analysis...")
        print()

        # Collect all statistics
        stats = {
            "basic_stats": self.get_basic_stats(),
            "temporal_analysis": self.get_temporal_analysis(),
            "agent_performance": self.get_agent_performance(),
            "feedback_messages": self.get_feedback_messages_analysis(),
            "session_analysis": self.get_session_analysis(),
        }

        # Generate insights
        stats["insights"] = self.generate_insights(stats)

        # Print report
        self.print_report(stats, table_limit)

        # Export if requested
        if export:
            self.export_data(stats, export_format)

        return stats

    def close(self):
        """Close MongoDB connection"""
        if hasattr(self, "client"):
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description="JU Bot Feedback Analytics")
    parser.add_argument("--export", action="store_true", help="Export data to file")
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Export format (default: json)",
    )
    parser.add_argument(
        "--table-only",
        action="store_true",
        help="Show only feedback table without full report",
    )
    parser.add_argument(
        "--table-limit",
        type=int,
        default=20,
        help="Number of feedback entries to show in table (default: 20)",
    )

    args = parser.parse_args()

    analytics = FeedbackAnalytics()

    try:
        if args.table_only:
            # Show only the feedback table
            print("🚀 JU Bot Feedback Table")
            print("=" * 50)
            analytics.print_feedback_table(limit=args.table_limit)
        else:
            # Run full analysis
            analytics.run_analysis(
                export=args.export,
                export_format=args.format,
                table_limit=args.table_limit,
            )
    except KeyboardInterrupt:
        print("\n⏹️ Analysis interrupted by user")
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
    finally:
        analytics.close()


if __name__ == "__main__":
    main()
