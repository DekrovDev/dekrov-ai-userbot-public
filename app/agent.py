"""AI-powered decision and action generation for incoming messages.

This module provides:
- decide_action(): Analyze message and choose action type
- generate_action_plan(): Create structured execution plan
- execute_plan(): Run the plan using existing tools
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pyrogram.types import Message

from ai.groq_client import GroqClient
from live.live_router import LiveDataRouter
from actions.action_executor import ActionExecutor

LOGGER = logging.getLogger("assistant.agent")

DECISION_PROMPT = """
You are the decision engine of a Telegram AI userbot.

Available actions:
- respond_text: Generate a normal AI reply
- search: Use external search tools (web, weather, rates)
- action: Execute Telegram actions (send, delete, manage)
- ignore: Do nothing (spam, noise, low-value)

Rules:
- Choose exactly ONE action
- Prefer search if real-time info is needed (weather, news, facts)
- Prefer action if user asks to DO something (send, delete, manage)
- Ignore spam, noise, or low-value messages
- Be decisive, do not hedge

Output ONLY JSON:
{{
  "action": "respond_text | search | action | ignore",
  "reason": "short technical explanation",
  "confidence": 0.0-1.0
}}

INPUT:
message: "{message}"
sender: {sender}
chat_type: {chat_type}
context_summary:
{context_summary}
"""

ACTION_PLAN_PROMPT = """
You are the action generator of a Telegram AI userbot.

Available action types:
- respond_text: Generate AI reply
- search: Use live tools (weather, web, rates)
- action: Execute Telegram actions

Rules:
- Output JSON only
- No explanations
- Be precise with arguments
- Never invent tools outside allowed ones

If action = respond_text:
{{
  "type": "respond_text",
  "text_instruction": "what kind of reply should be generated"
}}

If action = search:
{{
  "type": "search",
  "tool": "weather | web | rates",
  "args": {{
    "query": "...",
    "location": "...",
    "extra": "..."
  }}
}}

If action = action:
{{
  "type": "action",
  "name": "send_message | delete_message",
  "args": {{
    "chat_id": "...",
    "text": "...",
    "reply_to": "..."
  }}
}}

INPUT:
message: "{message}"
decision_action: "{action}"
context_summary:
{context_summary}
"""


class MessageAgent:
    """AI-powered message decision and action generator."""

    def __init__(
        self,
        groq_client: GroqClient,
        live_router: LiveDataRouter | None = None,
        action_executor: ActionExecutor | None = None,
        client=None,  # Pyrogram Client
    ) -> None:
        self._groq_client = groq_client
        self._live_router = live_router
        self._action_executor = action_executor
        self._client = client

    async def decide_action(
        self,
        message_text: str,
        sender: str,
        chat_type: str,
        context_summary: str = "",
    ) -> dict[str, Any]:
        """Analyze message and decide on action type.

        Args:
            message_text: The incoming message text
            sender: Sender description (owner, user, bot)
            chat_type: Type of chat (private, group, supergroup)
            context_summary: Extra runtime context about interface and chat state

        Returns:
            Decision dict with action, reason, confidence
        """
        prompt = DECISION_PROMPT.format(
            message=message_text[:200],
            sender=sender,
            chat_type=chat_type,
            context_summary=(context_summary or "n/a")[:1200],
        )

        try:
            result = await self._groq_client.generate_reply(
                prompt,
                reply_mode="command",
                response_mode="no_prefix",
                response_style_mode="NORMAL",
            )

            decision_text = result.text.strip()

            # Parse JSON from response
            if decision_text.startswith("```json"):
                decision_text = decision_text[7:-3].strip()
            elif decision_text.startswith("```"):
                decision_text = decision_text[3:-3].strip()

            decision = json.loads(decision_text)

            # Validate decision
            if decision.get("action") not in {
                "respond_text",
                "search",
                "action",
                "ignore",
            }:
                LOGGER.warning("invalid_action_type action=%s", decision.get("action"))
                return {
                    "action": "respond_text",
                    "reason": "Invalid action type, defaulting to respond_text",
                    "confidence": 0.5,
                }

            return decision

        except json.JSONDecodeError as e:
            LOGGER.error("decision_json_parse_error error=%s", e)
            return {
                "action": "respond_text",
                "reason": "JSON parse error, defaulting to respond_text",
                "confidence": 0.5,
            }
        except Exception as e:
            LOGGER.error("decision_failed error=%s", e)
            return {
                "action": "respond_text",
                "reason": f"Decision failed: {e}, defaulting to respond_text",
                "confidence": 0.5,
            }

    async def generate_action_plan(
        self,
        message_text: str,
        decision: dict[str, Any],
        context_summary: str = "",
    ) -> dict[str, Any]:
        """Generate structured action plan from decision.

        Args:
            message_text: The incoming message text
            decision: Decision dict from decide_action()
            context_summary: Extra runtime context about interface and chat state

        Returns:
            Action plan dict with type and args
        """
        action_type = decision.get("action", "respond_text")

        prompt = ACTION_PLAN_PROMPT.format(
            message=message_text[:200],
            action=action_type,
            context_summary=(context_summary or "n/a")[:1200],
        )

        try:
            result = await self._groq_client.generate_reply(
                prompt,
                reply_mode="command",
                response_mode="no_prefix",
                response_style_mode="NORMAL",
            )

            plan_text = result.text.strip()

            # Parse JSON from response
            if plan_text.startswith("```json"):
                plan_text = plan_text[7:-3].strip()
            elif plan_text.startswith("```"):
                plan_text = plan_text[3:-3].strip()

            plan = json.loads(plan_text)

            # Validate plan
            if plan.get("type") not in {"respond_text", "search", "action"}:
                LOGGER.warning("invalid_plan_type type=%s", plan.get("type"))
                return {
                    "type": "respond_text",
                    "text_instruction": "Generate a normal reply",
                }

            return plan

        except json.JSONDecodeError as e:
            LOGGER.error("plan_json_parse_error error=%s", e)
            return {
                "type": "respond_text",
                "text_instruction": "JSON parse error, generate normal reply",
            }
        except Exception as e:
            LOGGER.error("plan_generation_failed error=%s", e)
            return {
                "type": "respond_text",
                "text_instruction": f"Plan generation failed: {e}",
            }

    async def execute_plan(
        self,
        plan: dict[str, Any],
        message: Message,
    ) -> None:
        """Execute action plan.

        Args:
            plan: Action plan from generate_action_plan()
            message: Original Pyrogram message
        """
        plan_type = plan.get("type", "respond_text")

        if plan_type == "respond_text":
            await self._execute_respond_text(plan, message)
        elif plan_type == "search":
            await self._execute_search(plan, message)
        elif plan_type == "action":
            await self._execute_action(plan, message)
        else:
            LOGGER.warning("unknown_plan_type type=%s", plan_type)

    async def _execute_respond_text(
        self,
        plan: dict[str, Any],
        message: Message,
    ) -> None:
        """Generate AI text response."""
        instruction = plan.get("text_instruction", "Generate a normal reply")

        # Build prompt from instruction and message context
        message_text = getattr(message, "text", "") or ""
        prompt = f"{instruction}\n\nContext: {message_text[:200]}"

        try:
            result = await self._groq_client.generate_reply(
                prompt,
                reply_mode="command",
                response_mode="no_prefix",
                response_style_mode="NORMAL",
            )

            if self._client:
                await self._client.send_message(
                    chat_id=message.chat.id,
                    text=result.text,
                    reply_to_message_id=message.id,
                )
            else:
                LOGGER.warning("respond_text_skipped client_not_available")

        except Exception as e:
            LOGGER.error("respond_text_failed error=%s", e)

    async def _execute_search(
        self,
        plan: dict[str, Any],
        message: Message,
    ) -> None:
        """Execute search using live tools."""
        tool = plan.get("tool", "web")
        args = plan.get("args", {})

        if not self._live_router:
            LOGGER.warning("search_failed live_router_not_available")
            return

        try:
            if tool == "weather":
                location = args.get("location", "")
                query = args.get("query", f"Ð¿Ð¾Ð³Ð¾Ð´Ð° Ð² {location}")
                result = await self._live_router.route(query)
            elif tool == "rates":
                query = args.get("query", "currency rates")
                result = await self._live_router.route(query)
            else:  # web
                query = args.get("query", "")
                result = await self._live_router.route(query)

            if result:
                await self._client.send_message(
                    chat_id=message.chat.id,
                    text=result,
                    reply_to_message_id=message.id,
                )
            else:
                await self._client.send_message(
                    chat_id=message.chat.id,
                    text="Search returned no results.",
                    reply_to_message_id=message.id,
                )

        except Exception as e:
            LOGGER.error("search_failed error=%s", e)

    async def _execute_action(
        self,
        plan: dict[str, Any],
        message: Message,
    ) -> None:
        """Execute Telegram action."""
        action_name = plan.get("name", "send_message")
        args = plan.get("args", {})

        if not self._action_executor:
            LOGGER.warning("action_failed action_executor_not_available")
            return

        try:
            # Build action request from plan
            if action_name == "send_message":
                await self._client.send_message(
                    chat_id=args.get("chat_id", message.chat.id),
                    text=args.get("text", ""),
                    reply_to_message_id=args.get("reply_to", message.id),
                )
            elif action_name == "delete_message":
                await self._client.delete_messages(
                    chat_id=args.get("chat_id", message.chat.id),
                    message_ids=args.get("message_ids", [message.id]),
                )
            else:
                LOGGER.warning("unknown_action_name name=%s", action_name)

        except Exception as e:
            LOGGER.error("action_failed error=%s", e)

