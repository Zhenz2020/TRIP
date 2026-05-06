from __future__ import annotations

from dataclasses import dataclass

from .core import Agent, GlobalContext


@dataclass(frozen=True)
class Orchestrator:
    agents: list[Agent]

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        for a in self.agents:
            ctx = a.run(ctx=ctx)
        return ctx

