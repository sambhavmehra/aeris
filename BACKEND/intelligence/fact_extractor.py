"""
AERIS Fact Extractor — Extract semantic facts and entities from user prompts, agent thoughts, or tool results.
"""

import json
import logging
import re
from ai_engine import ai_engine

logger = logging.getLogger("aeris.intelligence.fact_extractor")


class FactExtractor:
    """Semantic fact extraction engine using LLM classification/extraction."""

    @staticmethod
    async def extract_facts_async(role: str, content: str) -> list[str]:
        """
        Analyze a message or tool output asynchronously.
        Extracts key entities, configurations, actions, or details as a JSON list of facts.
        """
        if not content or not isinstance(content, str):
            return []

        content_snippet = content[:3000].strip()  # Cap content to avoid massive context blowups
        if not content_snippet:
            return []

        prompt = (
            f"You are the AERIS Memory Fact Extractor. Analyze the following conversational payload from '{role}' "
            f"and extract key, concrete, long-term semantic facts, entities, technical details, tools used, configuration items, "
            f"or preferences. Ignore casual chat, greetings, and generic questions.\n\n"
            f"Example facts to extract:\n"
            f"- 'Current App: YouTube Shorts'\n"
            f"- 'TV Show: Taarak Mehta Ka Ooltah Chashmah'\n"
            f"- 'Target Domain: google.com'\n"
            f"- 'Active Project: AERIS Hybrid Memory Upgrade'\n"
            f"- 'User Name: Sambhav Mehra'\n"
            f"- 'Programming Language: Python'\n\n"
            f"Payload to analyze:\n"
            f'"{content_snippet}"\n\n'
            f"Respond with ONLY a valid JSON array of strings containing the extracted facts. "
            f"If no significant concrete technical facts, configurations, or entities are found, return an empty array []."
        )

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            
            # Clean markdown code blocks if any
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE)
                raw = re.sub(r"```$", "", raw).strip()
            
            # Attempt to locate JSON array structure if LLM returned verbose text
            if not raw.startswith("["):
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                if match:
                    raw = match.group(0)
            
            data = json.loads(raw)
            if isinstance(data, list):
                # Filter out non-string/empty entries and cleanup whitespace
                facts = [str(f).strip() for f in data if f]
                logger.info(f"Extracted facts: {facts}")
                return facts
            else:
                logger.warning(f"Fact extractor returned non-list JSON: {data}")
                return []
        except Exception as e:
            logger.warning(f"Failed to extract facts asynchronously: {e}")
            return []
