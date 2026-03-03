from src.agent.tools.search_regulations import search_regulations
from src.agent.tools.generate_answer import generate_answer
from src.agent.tools.registry import REGULATORY_PARTS

all_tools = [search_regulations, generate_answer]

__all__ = ["all_tools", "REGULATORY_PARTS", "search_regulations", "generate_answer"]
