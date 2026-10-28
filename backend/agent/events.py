from dataclasses import dataclass, field
from typing import Literal

AgentEventType = Literal["thinking", "tool_call", "tool_result", "export", "sources", "answer"]


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict = field(default_factory=dict)
