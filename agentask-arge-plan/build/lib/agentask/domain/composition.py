"""Kontrollü iş birleştirme (MVP sonrası faz; COMPOSITION_ENABLED ile açılır).

Düğümler: call_operation (etkin yayındaki onaylı işlem), if (koşul + then), for_each (açık ve sınırlı öğe listesi).
Statik doğrulama: bilinmeyen işlem, argüman uyumu, derinlik, öğe sayısı, düzleştirilmiş adım bütçesi. Düzleştirme
derleme zamanındadır; çalışma zamanında koşul yalnız guard'ı açar/kapatır, yeni komut üretmez.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentask.domain.actions import ActionSet
from agentask.domain.catalog import OperationDraft, compile_operation
from agentask.domain.commands import Condition


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CallOperation(_Node):
    kind: Literal["call_operation"]
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")
    arguments: dict[str, str] = Field(default_factory=dict)


class IfNode(_Node):
    kind: Literal["if"]
    condition: Condition
    then: list[Node] = Field(min_length=1, max_length=50)


class ForEach(_Node):
    kind: Literal["for_each"]
    variable: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    items: list[Annotated[str, Field(max_length=500)]] = Field(min_length=1, max_length=1000)
    body: list[Node] = Field(min_length=1, max_length=50)


Node = Annotated[CallOperation | IfNode | ForEach, Field(discriminator="kind")]
IfNode.model_rebuild()
ForEach.model_rebuild()


class CompositePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[Node] = Field(min_length=1, max_length=50)


class CompositionRejected(ValueError):
    pass


def compile_composite(
    plan: CompositePlan,
    lookup: Callable[[str], OperationDraft | None],
    actions: ActionSet,
    *,
    max_depth: int,
    max_items: int,
    max_steps: int,
) -> list[dict[str, Any]]:
    """Düzleştirilmiş [{command, when}] listesi. when: {"step": i, "is": True} → i. adımın koşulu sağlanmalı."""
    entries: list[dict[str, Any]] = []

    def add(command: dict[str, Any], when: dict[str, Any] | None) -> int:
        entries.append({"command": command, "when": when})
        if len(entries) > max_steps:
            raise CompositionRejected("too_many_steps")
        return len(entries) - 1

    def walk(nodes: list[Any], depth: int, when: dict[str, Any] | None, scope: dict[str, str]) -> None:
        if depth > max_depth:
            raise CompositionRejected("too_deep")
        for node in nodes:
            if isinstance(node, CallOperation):
                op = lookup(node.operation_id)
                if op is None:
                    raise CompositionRejected("unknown_operation")
                args = {k: v.format_map(scope) if scope else v for k, v in node.arguments.items()}
                try:
                    commands = compile_operation(op, args, actions)
                except (ValueError, KeyError) as exc:
                    raise CompositionRejected(f"argument_error:{exc}") from None
                for command in commands:
                    add(command, when)
            elif isinstance(node, IfNode):
                guard = add(
                    {"op": "evaluate_condition", "condition": node.condition.model_dump(mode="json")}, when
                )
                walk(node.then, depth + 1, {"step": guard, "is": True}, scope)
            else:
                if len(node.items) > max_items:
                    raise CompositionRejected("too_many_items")
                for item in node.items:
                    walk(node.body, depth + 1, when, {**scope, node.variable: item})

    walk(plan.nodes, 1, None, {})
    return entries
