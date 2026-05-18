"""
AERIS AI OS — Vision Tools Adapter
Exposes ComputerUseEngine capabilities to the Universal Tool Registry.
"""
import asyncio
from typing import Dict, Any

from tools.universal_registry import get_universal_registry
from tools.tool_interface import UniversalToolDef, ToolSource, RiskLevel, ToolInputSchema, ParamSchema
from automation.computer_use import ComputerUseEngine

# Singleton instance
_vision_engine = ComputerUseEngine()

registry = get_universal_registry()

# ==============================================================================
# 1. Vision Execute Task (Full autonomy)
# ==============================================================================
def vision_execute_task(instruction: str, max_steps: int = 5) -> Dict[str, Any]:
    """Execute a multi-step vision-based UI task autonomously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        result = asyncio.run(_vision_engine.execute_task(instruction, max_steps))
        return result.to_dict()
    except Exception as e:
        return {"success": False, "error": str(e)}

registry.register_tool(
    UniversalToolDef(
        name="vision_execute_task",
        description="Autonomously execute a multi-step computer task by seeing the screen and interacting with UI elements (e.g., 'Click the search bar and type hello').",
        category="system",
        source=ToolSource.BUILTIN,
        risk_level=RiskLevel.MEDIUM,
        input_schema=ToolInputSchema(
            params=[
                ParamSchema(name="instruction", type="string", description="The task instruction", required=True),
                ParamSchema(name="max_steps", type="integer", description="Maximum steps to take", required=False, default=5)
            ]
        ),
        func=vision_execute_task
    )
)

# ==============================================================================
# 2. Vision Click Element
# ==============================================================================
def vision_click_element(description: str) -> Dict[str, Any]:
    """Find and click a specific UI element on screen."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        result = asyncio.run(_vision_engine.click_element(description))
        return result.to_dict()
    except Exception as e:
        return {"success": False, "error": str(e)}

registry.register_tool(
    UniversalToolDef(
        name="vision_click_element",
        description="Find and click a specific UI element on the screen using AI vision.",
        category="system",
        source=ToolSource.BUILTIN,
        risk_level=RiskLevel.LOW,
        input_schema=ToolInputSchema(
            params=[
                ParamSchema(name="description", type="string", description="Description of the element to click", required=True)
            ]
        ),
        func=vision_click_element
    )
)

# ==============================================================================
# 3. Vision Type In Field
# ==============================================================================
def vision_type_in_field(field_description: str, text: str) -> Dict[str, Any]:
    """Find a field and type text into it."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        result = asyncio.run(_vision_engine.type_in_field(field_description, text))
        return result.to_dict()
    except Exception as e:
        return {"success": False, "error": str(e)}

registry.register_tool(
    UniversalToolDef(
        name="vision_type_in_field",
        description="Find a text field on screen and type text into it.",
        category="system",
        source=ToolSource.BUILTIN,
        risk_level=RiskLevel.LOW,
        input_schema=ToolInputSchema(
            params=[
                ParamSchema(name="field_description", type="string", description="Description of the text field", required=True),
                ParamSchema(name="text", type="string", description="The text to type", required=True)
            ]
        ),
        func=vision_type_in_field
    )
)

# ==============================================================================
# 4. Vision Find Element
# ==============================================================================
def vision_find_element(description: str) -> Dict[str, Any]:
    """Locate a UI element and return its coordinates without clicking."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return asyncio.run(_vision_engine.find_element(description))
    except Exception as e:
        return {"success": False, "error": str(e)}

registry.register_tool(
    UniversalToolDef(
        name="vision_find_element",
        description="Find a UI element on screen and return its X, Y coordinates without clicking it.",
        category="system",
        source=ToolSource.BUILTIN,
        risk_level=RiskLevel.LOW,
        input_schema=ToolInputSchema(
            params=[
                ParamSchema(name="description", type="string", description="Description of the element to find", required=True)
            ]
        ),
        func=vision_find_element
    )
)
