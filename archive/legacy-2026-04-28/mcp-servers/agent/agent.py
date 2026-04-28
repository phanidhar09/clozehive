"""
CLOZEHIVE Wardrobe Agent
========================
A LangChain ReAct agent that connects to all four MCP servers via
MultiServerMCPClient and orchestrates tool calls to answer wardrobe,
outfit, packing, and vision questions.

Usage (standalone test):
    python agent.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from shared.config import get_settings
from shared.logger import get_logger

logger = get_logger("agent")

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are CLOZEHIVE AI, an expert personal fashion stylist and wardrobe assistant.

You have access to the following tools via connected MCP servers:

WEATHER TOOLS  (weather server):
  • get_weather_forecast   — day-by-day forecast for a destination and date range
  • get_weather_summary    — aggregated summary: dominant condition, avg temps, rainy days

OUTFIT TOOLS  (outfit server):
  • generate_outfit_suggestions — 3 AI-curated outfit combinations from the user's closet
  • get_style_tips              — general styling advice for occasion + weather

PACKING TOOLS  (packing server):
  • generate_trip_packing_list  — full packing list matched to closet + weather
  • get_packing_checklist       — generic checklist when no closet data is available

VISION TOOLS  (vision server):
  • analyze_garment_image — analyse a clothing image and extract garment attributes

Guidelines:
- For packing requests: ALWAYS call get_weather_summary first, then pass its JSON output
  directly to generate_trip_packing_list.
- For outfit requests: call generate_outfit_suggestions with the user's closet items as JSON.
- For image analysis: call analyze_garment_image with the base64 image string.
- Always explain your reasoning clearly and present results in a readable, friendly format.
- When items are missing from the closet, suggest what to purchase.
- Be concise but thorough. Use bullet points for lists.
""".strip()


def _get_server_config(settings) -> dict[str, Any]:
    """Build the MultiServerMCPClient server configuration dict."""
    return {
        "weather": {
            "transport": "sse",
            "url": settings.weather_sse_url,
        },
        "outfit": {
            "transport": "sse",
            "url": settings.outfit_sse_url,
        },
        "packing": {
            "transport": "sse",
            "url": settings.packing_sse_url,
        },
        "vision": {
            "transport": "sse",
            "url": settings.vision_sse_url,
        },
    }


class WardrobeAgent:
    """
    Persistent wardrobe agent — initialised once, reused across requests.
    Holds an open MultiServerMCPClient connection and a compiled LangGraph agent.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: MultiServerMCPClient | None = None
        self._agent = None
        self._tools: list = []

    async def start(self) -> None:
        """Open connections to all MCP servers and compile the agent."""
        logger.info("Connecting to MCP servers …")
        server_config = _get_server_config(self._settings)

        self._client = MultiServerMCPClient(server_config)
        self._tools = await self._client.get_tools()
        logger.info("Loaded %d tools from MCP servers", len(self._tools))
        for tool in self._tools:
            logger.info("  ✓ %s.%s", tool.name.split("__")[0] if "__" in tool.name else "mcp", tool.name)

        model = ChatOpenAI(
            model=self._settings.openai_model,
            temperature=0.7,
            api_key=self._settings.openai_api_key,
            streaming=True,
        )

        self._agent = create_react_agent(
            model,
            self._tools,
            prompt=SYSTEM_PROMPT,
        )
        logger.info("Wardrobe agent ready")

    async def stop(self) -> None:
        """Release MCP client reference (langchain-mcp-adapters 0.1+ has no async context exit)."""
        self._client = None
        self._tools = []
        logger.info("MCP client released")

    async def chat(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Send a message to the wardrobe agent and return its response.

        Args:
            message: The user's latest message.
            history: Optional list of prior messages as {'role': 'user'|'assistant', 'content': str}.

        Returns:
            The agent's response as a plain string.
        """
        if self._agent is None:
            raise RuntimeError("Agent not started — call await agent.start() first")

        messages = []

        # Inject conversation history
        if history:
            for msg in history[-10:]:  # cap at last 10 turns
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=message))

        logger.info("Agent invoked — message: %.80s …", message)
        result = await self._agent.ainvoke({"messages": messages})

        # Extract final text response from LangGraph output
        output_messages = result.get("messages", [])
        if output_messages:
            last = output_messages[-1]
            response = last.content if hasattr(last, "content") else str(last)
        else:
            response = "I couldn't generate a response. Please try again."

        logger.info("Agent response: %.80s …", response)
        return response

    @property
    def available_tools(self) -> list[str]:
        return [t.name for t in self._tools]


# ── Singleton instance ────────────────────────────────────────────────────────

_agent_instance: WardrobeAgent | None = None


def get_agent() -> WardrobeAgent:
    """Return the module-level singleton agent (must call start() before use)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = WardrobeAgent()
    return _agent_instance


# ── Standalone test ───────────────────────────────────────────────────────────

async def _demo() -> None:
    """Quick smoke test — run with: python agent.py"""
    import asyncio

    agent = WardrobeAgent()
    await agent.start()

    try:
        response = await agent.chat(
            "What should I pack for a 5-day beach holiday in Bali starting 2025-07-01? "
            "I have: white t-shirt (casual), blue shorts (casual), sandals, sunglasses."
        )
        print("\n=== Agent Response ===")
        print(response)
    finally:
        await agent.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_demo())
