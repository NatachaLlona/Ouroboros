"""Compose exactly one identity policy with the common safety rules."""
from dataclasses import dataclass
from types import MappingProxyType
from assistance.common_instructions import COMMON_INSTRUCTIONS
from assistance.assistant_1_instructions import ASSISTANT_1_INSTRUCTIONS
from assistance.assistant_2_instructions import ASSISTANT_2_INSTRUCTIONS
from shared.assistant_identity import ASSISTANT_1, ASSISTANT_2


@dataclass(frozen=True)
class AssistantPolicy:
    instructions: str
    context: str
    tools: tuple[str, ...]
    enabled: bool


ASSISTANT_POLICIES = MappingProxyType({
    ASSISTANT_1: AssistantPolicy(ASSISTANT_1_INSTRUCTIONS, 'site', (), False),
    ASSISTANT_2: AssistantPolicy(ASSISTANT_2_INSTRUCTIONS, 'active_form', ('catalogue_get',), True),
})


def instructions_for(assistant_id):
    """No fallback to another identity's instructions, context or tools."""
    policy = ASSISTANT_POLICIES[assistant_id]
    return COMMON_INSTRUCTIONS + '\n' + policy.instructions
