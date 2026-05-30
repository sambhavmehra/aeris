# -*- coding: utf-8 -*-
"""
AERIS Assembly Sequence Engine
Orchestrates the cinematic agent assembly sequence via SSE events.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator
from services.voice_profiles import get_all_agent_ids, VOICE_PROFILES

logger = logging.getLogger(__name__)

class AssemblyEngine:
    """Orchestrates the cinematic agent assembly sequence via SSE events."""

    async def run_assembly(self) -> AsyncGenerator[str, None]:
        """Yields SSE-formatted events for the full assembly sequence.

        Phase 1: Core Activation (7 loading steps, ~400ms each)
        Phase 2: Agent Arrival (32 agents, yields events for each)
        Phase 3: Synchronization (6 sync steps, ~500ms each)
        Phase 4: Final Report
        """
        try:
            logger.info("AERIS Assembly Sequence started.")
            
            # --- Phase 1: Core Activation ---
            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'core-init'})}\n\n"
            await asyncio.sleep(0.2)

            loading_labels = [
                "Neural Systems",
                "Agent Registry",
                "Voice Profiles",
                "Memory Layer",
                "Tool Framework",
                "Swarm Network",
                "Security Layer"
            ]

            for i, label in enumerate(loading_labels):
                # Simulating progression
                for progress in [20, 50, 80, 100]:
                    yield f"data: {json.dumps({'type': 'loading_step', 'index': i, 'label': label, 'progress': progress, 'complete': (progress == 100)})}\n\n"
                    await asyncio.sleep(0.1) # Total 400ms per loading bar
                await asyncio.sleep(0.1)

            # --- Phase 2: Agent Arrival ---
            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'agent-arrival'})}\n\n"
            await asyncio.sleep(0.5)

            # Categorize the agents in the order they should arrive
            # Core and Control agents (first 16)
            # Swarm agents (9)
            # Special agents (7)
            agent_ids = get_all_agent_ids()
            
            for index, agent_id in enumerate(agent_ids):
                profile = VOICE_PROFILES.get(agent_id, {})
                codename = profile.get("codename", agent_id.upper())
                role = profile.get("role", "Agent")
                intro_text = profile.get("intro", f"Agent {codename} online.")
                voice = profile.get("voice", "hi-IN-MadhurNeural")
                pitch = profile.get("pitch", "+0Hz")
                rate = profile.get("rate", "+0%")
                
                # Determine category based on registry structure
                category = "core"
                if agent_id in ["judge", "watcher", "genesis", "vigil"]:
                    category = "control"
                elif agent_id in ["nexus", "archon", "forge", "insight", "scribe", "sentinel", "pulse", "atlas", "command"]:
                    category = "swarm"
                elif agent_id in ["hunter", "reaper", "ghost", "webweaver", "strategos", "validator", "blueprint"]:
                    category = "special"

                # Trigger initializing state (means agent is introducing themselves)
                yield f"data: {json.dumps({'type': 'agent_status', 'agent_id': agent_id, 'status': 'initializing', 'index': index, 'codename': codename, 'role': role, 'category': category, 'intro': intro_text})}\n\n"
                
                # Wait a bit after status update so the UI animation settles before speaking starts
                await asyncio.sleep(0.3)
                
                # Slow down the configured speech rate slightly for a more deliberate, cinematic feel
                try:
                    rate_val = int(rate.replace("%", ""))
                    slower_rate = f"{'' if rate_val - 6 < 0 else '+'}{rate_val - 6}%"
                except Exception:
                    slower_rate = "-6%"

                # Speak introduction using backend TTS (non-blocking for asyncio)
                try:
                    from services.texttospeech import text_to_speech
                    await asyncio.to_thread(
                        text_to_speech,
                        intro_text,
                        voice=voice,
                        pitch=pitch,
                        rate=slower_rate,
                        max_spoken_sentences=3,
                        max_spoken_chars=400
                    )
                except Exception as e:
                    logger.error(f"Error speaking intro for {agent_id}: {e}")

                # Trigger online state (only after intro finished)
                yield f"data: {json.dumps({'type': 'agent_status', 'agent_id': agent_id, 'status': 'online', 'index': index, 'codename': codename, 'role': role, 'category': category})}\n\n"
                
                # Brief stagger delay before next agent starts
                await asyncio.sleep(0.25)

            # --- Phase 3: Synchronization ---
            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'network-sync'})}\n\n"
            await asyncio.sleep(0.5)

            sync_labels = [
                "Voice Synchronization",
                "Memory Synchronization",
                "Capability Mapping",
                "Tool Registration",
                "Swarm Coordination",
                "Security Validation"
            ]

            for i, label in enumerate(sync_labels):
                for progress in [25, 60, 100]:
                    yield f"data: {json.dumps({'type': 'sync_step', 'index': i, 'label': label, 'progress': progress, 'complete': (progress == 100)})}\n\n"
                    await asyncio.sleep(0.16) # Total 500ms per step
                await asyncio.sleep(0.1)

            # --- Phase 4: Final Complete Report ---
            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'final'})}\n\n"
            await asyncio.sleep(0.5)
            yield f"data: {json.dumps({'type': 'complete', 'total_agents': len(agent_ids)})}\n\n"
            logger.info("AERIS Assembly Sequence complete. 32 agents assembled.")

        except asyncio.CancelledError:
            logger.warning("Assembly streaming was cancelled.")
        except Exception as e:
            logger.error(f"Error during assembly sequence: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def run_disassembly(self) -> AsyncGenerator[str, None]:
        """Quick reverse shutdown sequence."""
        try:
            logger.info("AERIS Disassembly Sequence started.")
            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'disassembling'})}\n\n"
            
            agent_ids = get_all_agent_ids()
            # Reverse order of agents
            for agent_id in reversed(agent_ids):
                yield f"data: {json.dumps({'type': 'agent_status', 'agent_id': agent_id, 'status': 'offline'})}\n\n"
                await asyncio.sleep(0.1) # 100ms between each offline state

            yield f"data: {json.dumps({'type': 'phase_change', 'phase': 'idle'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'disassembled': True})}\n\n"
            logger.info("AERIS Disassembly Sequence complete. All agents disassembled.")

        except asyncio.CancelledError:
            logger.warning("Disassembly streaming was cancelled.")
        except Exception as e:
            logger.error(f"Error during disassembly sequence: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
