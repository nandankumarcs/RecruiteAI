"""Tool schema contracts for call v2 agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ToolArgumentKind = Literal["string", "integer", "number", "boolean", "object", "array", "any"]


@dataclass(frozen=True, slots=True)
class ToolArgumentSpec:
    name: str
    kind: ToolArgumentKind
    required: bool = True
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    arguments: list[ToolArgumentSpec] = field(default_factory=list)
    side_effecting: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def argument_by_name(self) -> dict[str, ToolArgumentSpec]:
        return {argument.name: argument for argument in self.arguments}


def validate_tool_arguments(
    *,
    tool: ToolSpec,
    arguments: dict[str, Any],
) -> None:
    specs = tool.argument_by_name()
    for name, spec in specs.items():
        if spec.required and name not in arguments:
            raise ValueError(f"missing required argument {name!r} for tool {tool.name!r}")
        if name in arguments and not _matches_kind(arguments[name], spec.kind):
            raise ValueError(
                f"argument {name!r} for tool {tool.name!r} must be {spec.kind}"
            )

    unknown = set(arguments) - set(specs)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown argument(s) for tool {tool.name!r}: {names}")


def _matches_kind(value: Any, kind: ToolArgumentKind) -> bool:
    if kind == "any":
        return True
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (isinstance(value, int | float) and not isinstance(value, bool))
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    return False
