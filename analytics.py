#!/usr/bin/env python3
"""
JU Bot Analytics Script

This script connects to MongoDB and provides comprehensive analytics
about chat history, feedback, and user engagement.

Usage:
    python analytics.py [--export] [--format json|csv]
"""

import sys
import os
import argparse
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pymongo import MongoClient
from collections import defaultdict, Counter

# Add the current directory to Python path to import config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config


class JUBotAnalytics:
    def __init__(self):
        """Initialize MongoDB connection"""
        try:
            self.client = self._get_mongodb_client()
            mongo_config = config.MONGODB
            self.db = self.client[mongo_config["database"]]
            self.chat_collection = self.db["chat_history"]
            self.feedback_collection = self.db["feedback_data"]

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
            f"🔍 Connecting to MongoDB at {mongo_config['host']}:{mongo_config['port']}"
        )
        print(f"📊 Using database: {mongo_config['database']}")

        # Try authenticated connection with configured credentials first
        try:
            auth_connection = f"mongodb://{mongo_config['username']}:{mongo_config['password']}@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
            client = MongoClient(auth_connection)
            client.admin.command("ping")
            print("🔐 Connected with configured credentials")
            return client

        except Exception:
            # Fallback to admin credentials
            try:
                admin_connection = f"mongodb://admin:password@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
                client = MongoClient(admin_connection)
                client.admin.command("ping")
                print("🔐 Connected with admin credentials")
                return client

            except Exception:
                # Final fallback to no authentication
                try:
                    simple_connection = (
                        f"mongodb://{mongo_config['host']}:{mongo_config['port']}"
                    )
                    client = MongoClient(simple_connection)
                    client.admin.command("ping")
                    print("🔓 Connected without authentication")
                    return client

                except Exception as e:
                    print(f"❌ All connection attempts failed: {e}")
                    raise e

    def get_chat_analytics(self) -> Dict[str, Any]:
        """Get comprehensive chat analytics"""
        print("\n📊 Analyzing Chat Data...")

        # Basic chat statistics
        total_chats = self.chat_collection.count_documents({})
        active_chats = self.chat_collection.count_documents({"no_messages": False})
        empty_chats = total_chats - active_chats

        # Get all active chats
        active_chat_docs = list(self.chat_collection.find({"no_messages": False}))

        # Message statistics
        total_messages = sum(
            len(chat.get("chat_history", [])) for chat in active_chat_docs
        )
        avg_messages_per_chat = total_messages / active_chats if active_chats > 0 else 0

        # Message length analysis
        message_lengths = []
        question_lengths = []
        answer_lengths = []

        for chat in active_chat_docs:
            for msg in chat.get("chat_history", []):
                question = msg.get("question", "")
                answer = msg.get("answer", "")
                question_lengths.append(len(question))
                answer_lengths.append(len(answer))
                message_lengths.extend([len(question), len(answer)])

        # Time-based analysis
        chat_creation_times = []
        message_times = []

        for chat in active_chat_docs:
            if chat.get("created_at"):
                chat_creation_times.append(chat["created_at"])

            for msg in chat.get("chat_history", []):
                if msg.get("timestamp"):
                    message_times.append(msg["timestamp"])

        # Recent activity (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_chats = self.chat_collection.count_documents(
            {"created_at": {"$gte": seven_days_ago}}
        )

        return {
            "total_chats": total_chats,
            "active_chats": active_chats,
            "empty_chats": empty_chats,
            "total_messages": total_messages,
            "avg_messages_per_chat": round(avg_messages_per_chat, 2),
            "avg_question_length": (
                round(sum(question_lengths) / len(question_lengths), 2)
                if question_lengths
                else 0
            ),
            "avg_answer_length": (
                round(sum(answer_lengths) / len(answer_lengths), 2)
                if answer_lengths
                else 0
            ),
            "recent_chats_7d": recent_chats,
            "oldest_chat": min(chat_creation_times) if chat_creation_times else None,
            "newest_chat": max(chat_creation_times) if chat_creation_times else None,
        }

    def get_feedback_analytics(self) -> Dict[str, Any]:
        """Get comprehensive feedback analytics"""
        print("👍 Analyzing Feedback Data...")

        # Get all active chats with messages
        active_chats = list(self.chat_collection.find({"no_messages": False}))

        # Feedback statistics from chat history
        total_messages_with_feedback = 0
        thumbs_up_count = 0
        thumbs_down_count = 0
        neutral_count = 0
        general_feedback_count = 0
        thumbs_down_feedback_count = 0

        feedback_values = []
        thumb_ratios = []

        for chat in active_chats:
            chat_thumb_ratio = chat.get("thumb_ratio", 0)
            if chat_thumb_ratio > 0:
                thumb_ratios.append(chat_thumb_ratio)

            for msg in chat.get("chat_history", []):
                feedback_value = msg.get("feedback", 0)
                user_feedback_str = msg.get("user_feedback_str", "")
                thumbs_down_msg = msg.get("thumbs_down_message_feedback", "")

                if feedback_value != 0:
                    total_messages_with_feedback += 1
                    feedback_values.append(feedback_value)

                    if feedback_value == 1:
                        thumbs_up_count += 1
                    elif feedback_value == -1:
                        thumbs_down_count += 1
                else:
                    neutral_count += 1

                if user_feedback_str.strip():
                    general_feedback_count += 1

                if thumbs_down_msg.strip():
                    thumbs_down_feedback_count += 1

        # Legacy feedback collection analysis
        legacy_feedback_count = self.feedback_collection.count_documents({})
        legacy_thumbs_up = self.feedback_collection.count_documents(
            {"feedback_type": "thumbs_up"}
        )
        legacy_thumbs_down = self.feedback_collection.count_documents(
            {"feedback_type": "thumbs_down"}
        )
        legacy_general = self.feedback_collection.count_documents(
            {"feedback_type": "feedback"}
        )

        # Calculate averages
        total_messages = sum(len(chat.get("chat_history", [])) for chat in active_chats)
        feedback_rate = (
            (total_messages_with_feedback / total_messages * 100)
            if total_messages > 0
            else 0
        )
        avg_thumb_ratio = sum(thumb_ratios) / len(thumb_ratios) if thumb_ratios else 0

        return {
            "total_messages": total_messages,
            "messages_with_feedback": total_messages_with_feedback,
            "feedback_rate_percent": round(feedback_rate, 2),
            "thumbs_up_count": thumbs_up_count,
            "thumbs_down_count": thumbs_down_count,
            "neutral_count": neutral_count,
            "general_feedback_count": general_feedback_count,
            "thumbs_down_feedback_count": thumbs_down_feedback_count,
            "avg_thumb_ratio": round(avg_thumb_ratio, 3),
            "legacy_feedback_total": legacy_feedback_count,
            "legacy_thumbs_up": legacy_thumbs_up,
            "legacy_thumbs_down": legacy_thumbs_down,
            "legacy_general": legacy_general,
        }

    def get_engagement_analytics(self) -> Dict[str, Any]:
        """Get user engagement analytics"""
        print("📈 Analyzing User Engagement...")

        active_chats = list(self.chat_collection.find({"no_messages": False}))

        # Chat duration analysis
        chat_durations = []
        messages_per_chat = []

        for chat in active_chats:
            first_time = chat.get("first_message_time")
            last_time = chat.get("last_message_time")
            message_count = len(chat.get("chat_history", []))

            messages_per_chat.append(message_count)

            if first_time and last_time and first_time != last_time:
                duration = (last_time - first_time).total_seconds() / 60  # minutes
                chat_durations.append(duration)

        # Engagement levels
        single_message_chats = sum(1 for count in messages_per_chat if count == 1)
        short_chats = sum(1 for count in messages_per_chat if 2 <= count <= 3)
        medium_chats = sum(1 for count in messages_per_chat if 4 <= count <= 10)
        long_chats = sum(1 for count in messages_per_chat if count > 10)

        return {
            "avg_messages_per_chat": (
                round(sum(messages_per_chat) / len(messages_per_chat), 2)
                if messages_per_chat
                else 0
            ),
            "max_messages_in_chat": max(messages_per_chat) if messages_per_chat else 0,
            "min_messages_in_chat": min(messages_per_chat) if messages_per_chat else 0,
            "single_message_chats": single_message_chats,
            "short_chats_2_3": short_chats,
            "medium_chats_4_10": medium_chats,
            "long_chats_10plus": long_chats,
            "avg_chat_duration_minutes": (
                round(sum(chat_durations) / len(chat_durations), 2)
                if chat_durations
                else 0
            ),
            "max_chat_duration_minutes": (
                round(max(chat_durations), 2) if chat_durations else 0
            ),
        }

    def get_content_analytics(self) -> Dict[str, Any]:
        """Get content and topic analytics"""
        print("📝 Analyzing Content...")

        active_chats = list(self.chat_collection.find({"no_messages": False}))

        # Common words in questions
        question_words = []
        answer_words = []

        for chat in active_chats:
            for msg in chat.get("chat_history", []):
                question = msg.get("question", "").lower()
                answer = msg.get("answer", "").lower()

                # Simple word extraction (you could enhance this with NLP)
                question_words.extend(question.split())
                answer_words.extend(answer.split())

        # Filter out common stop words and get top words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "this",
            "that",
            "these",
            "those",
        }

        filtered_question_words = [
            word for word in question_words if len(word) > 2 and word not in stop_words
        ]
        filtered_answer_words = [
            word for word in answer_words if len(word) > 2 and word not in stop_words
        ]

        top_question_words = Counter(filtered_question_words).most_common(10)
        top_answer_words = Counter(filtered_answer_words).most_common(10)

        return {
            "total_question_words": len(question_words),
            "total_answer_words": len(answer_words),
            "unique_question_words": len(set(question_words)),
            "unique_answer_words": len(set(answer_words)),
            "top_question_words": top_question_words,
            "top_answer_words": top_answer_words,
        }

    def print_analytics_report(self):
        """Print a comprehensive analytics report"""
        print("\n" + "=" * 80)
        print("🤖 JU BOT ANALYTICS REPORT")
        print("=" * 80)
        print(f"📅 Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Chat Analytics
        chat_data = self.get_chat_analytics()
        print(f"\n📊 CHAT STATISTICS")
        print("-" * 40)
        print(f"Total Chats Created: {chat_data['total_chats']:,}")
        print(f"Active Chats (with messages): {chat_data['active_chats']:,}")
        print(f"Empty Chats: {chat_data['empty_chats']:,}")
        print(f"Total Messages: {chat_data['total_messages']:,}")
        print(f"Average Messages per Chat: {chat_data['avg_messages_per_chat']}")
        print(f"Average Question Length: {chat_data['avg_question_length']} characters")
        print(f"Average Answer Length: {chat_data['avg_answer_length']} characters")
        print(f"New Chats (Last 7 days): {chat_data['recent_chats_7d']:,}")

        if chat_data["oldest_chat"]:
            print(f"Oldest Chat: {chat_data['oldest_chat'].strftime('%Y-%m-%d %H:%M')}")
        if chat_data["newest_chat"]:
            print(f"Newest Chat: {chat_data['newest_chat'].strftime('%Y-%m-%d %H:%M')}")

        # Feedback Analytics
        feedback_data = self.get_feedback_analytics()
        print(f"\n👍 FEEDBACK STATISTICS")
        print("-" * 40)
        print(f"Total Messages: {feedback_data['total_messages']:,}")
        print(f"Messages with Feedback: {feedback_data['messages_with_feedback']:,}")
        print(f"Feedback Rate: {feedback_data['feedback_rate_percent']}%")
        print(f"👍 Thumbs Up: {feedback_data['thumbs_up_count']:,}")
        print(f"👎 Thumbs Down: {feedback_data['thumbs_down_count']:,}")
        print(f"😐 Neutral (no feedback): {feedback_data['neutral_count']:,}")
        print(
            f"💬 General Feedback Messages: {feedback_data['general_feedback_count']:,}"
        )
        print(
            f"📝 Thumbs Down Explanations: {feedback_data['thumbs_down_feedback_count']:,}"
        )
        print(f"Average Satisfaction Ratio: {feedback_data['avg_thumb_ratio']:.3f}")

        print(f"\n📋 LEGACY FEEDBACK SYSTEM")
        print("-" * 40)
        print(f"Total Legacy Feedback: {feedback_data['legacy_feedback_total']:,}")
        print(f"Legacy Thumbs Up: {feedback_data['legacy_thumbs_up']:,}")
        print(f"Legacy Thumbs Down: {feedback_data['legacy_thumbs_down']:,}")
        print(f"Legacy General Feedback: {feedback_data['legacy_general']:,}")

        # Engagement Analytics
        engagement_data = self.get_engagement_analytics()
        print(f"\n📈 ENGAGEMENT ANALYTICS")
        print("-" * 40)
        print(f"Average Messages per Chat: {engagement_data['avg_messages_per_chat']}")
        print(f"Longest Chat: {engagement_data['max_messages_in_chat']} messages")
        print(
            f"Shortest Active Chat: {engagement_data['min_messages_in_chat']} message(s)"
        )
        print(f"Single Message Chats: {engagement_data['single_message_chats']:,}")
        print(f"Short Chats (2-3 messages): {engagement_data['short_chats_2_3']:,}")
        print(f"Medium Chats (4-10 messages): {engagement_data['medium_chats_4_10']:,}")
        print(f"Long Chats (10+ messages): {engagement_data['long_chats_10plus']:,}")
        print(
            f"Average Chat Duration: {engagement_data['avg_chat_duration_minutes']} minutes"
        )
        print(
            f"Longest Chat Duration: {engagement_data['max_chat_duration_minutes']} minutes"
        )

        # Content Analytics
        content_data = self.get_content_analytics()
        print(f"\n📝 CONTENT ANALYTICS")
        print("-" * 40)
        print(f"Total Words in Questions: {content_data['total_question_words']:,}")
        print(f"Total Words in Answers: {content_data['total_answer_words']:,}")
        print(f"Unique Words in Questions: {content_data['unique_question_words']:,}")
        print(f"Unique Words in Answers: {content_data['unique_answer_words']:,}")

        print(f"\n🔤 TOP QUESTION WORDS")
        print("-" * 40)
        for word, count in content_data["top_question_words"]:
            print(f"{word}: {count}")

        print(f"\n🔤 TOP ANSWER WORDS")
        print("-" * 40)
        for word, count in content_data["top_answer_words"]:
            print(f"{word}: {count}")

        print("\n" + "=" * 80)
        print("✅ Analytics Report Complete")
        print("=" * 80)

    def export_analytics(self, format_type: str = "json", filename: str = None):
        """Export analytics data to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ju_bot_analytics_{timestamp}.{format_type}"

        # Collect all analytics data
        analytics_data = {
            "generated_at": datetime.now().isoformat(),
            "chat_analytics": self.get_chat_analytics(),
            "feedback_analytics": self.get_feedback_analytics(),
            "engagement_analytics": self.get_engagement_analytics(),
            "content_analytics": self.get_content_analytics(),
        }

        if format_type.lower() == "json":
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(analytics_data, f, indent=2, default=str, ensure_ascii=False)
        elif format_type.lower() == "csv":
            # Flatten the data for CSV export
            flattened_data = []
            for category, data in analytics_data.items():
                if category == "generated_at":
                    continue
                for key, value in data.items():
                    if isinstance(value, (list, dict)):
                        value = str(value)
                    flattened_data.append(
                        {"category": category, "metric": key, "value": value}
                    )

            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["category", "metric", "value"])
                writer.writeheader()
                writer.writerows(flattened_data)

        print(f"📁 Analytics exported to: {filename}")

    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description="JU Bot Analytics Script")
    parser.add_argument(
        "--export", action="store_true", help="Export analytics to file"
    )
    parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="Export format"
    )
    parser.add_argument("--filename", help="Custom filename for export")

    args = parser.parse_args()

    try:
        analytics = JUBotAnalytics()

        # Always print the report
        analytics.print_analytics_report()

        # Export if requested
        if args.export:
            analytics.export_analytics(args.format, args.filename)

        analytics.close_connection()

    except KeyboardInterrupt:
        print("\n⚠️ Analytics interrupted by user")
    except Exception as e:
        print(f"❌ Analytics failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
