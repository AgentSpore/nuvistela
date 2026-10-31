from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import SecretStr

from app.agent.deps import FamilyStateView, GameDeps
from app.agent.models import AgentEvent
from app.core.config import Settings


@dataclass
class StubFamilies:
    """Stub for the FamilyStateReader port; records the family ids it was asked about."""

    calls: list[str] = field(default_factory=list)

    async def get_state(self, family_id: str) -> FamilyStateView:
        self.calls.append(family_id)
        return FamilyStateView(family_title="The Ivanovs", member_names=("Anya", "Boris"))


@pytest.fixture
def families() -> StubFamilies:
    return StubFamilies()


@pytest.fixture
def make_settings():
    def build(**overrides) -> Settings:
        values: dict[str, Any] = {
            "database_url": "postgresql+asyncpg://u:p@localhost/x",
            "family_llm_model": "vendor/model-x",
            "openrouter_api_key": SecretStr("test-key"),
            **overrides,
        }
        return Settings(_env_file=None, **values)

    return build


@pytest.fixture
def deps_factory(families: StubFamilies):
    return lambda family_id: GameDeps(family_id=family_id, families=families)


@pytest.fixture
def event() -> AgentEvent:
    return AgentEvent(family_id="fam-1", channel="telegram", kind="message", text="What now?")
