from __future__ import annotations

from dataclasses import dataclass

from .action_models import ActionDefinition, ActionRequest, ActionRisk


@dataclass(slots=True)
class PolicyDecision:
    risk: ActionRisk
    requires_confirmation: bool
    impact_summary: str


class ActionPolicy:
    def evaluate(self, definition: ActionDefinition, request: ActionRequest) -> PolicyDecision:
        risk = self._resolve_risk(definition, request)
        return PolicyDecision(
            risk=risk,
            requires_confirmation=False,  # Owner commands execute directly without confirmation
            impact_summary=self._build_impact_summary(risk, request),
        )

    def _resolve_risk(self, definition: ActionDefinition, request: ActionRequest) -> ActionRisk:
        if definition.name == "cross_chat_request":
            subaction = str(request.arguments.get("subaction", "")).strip().lower()
            has_delivery_target = request.secondary_target is not None
            if subaction in {"direct_send", "forward_last"}:
                return ActionRisk.SENSITIVE
            if subaction in {"rewrite", "extract"} and has_delivery_target:
                return ActionRisk.SENSITIVE
            if subaction in {"summarize", "find", "inspect_chat", "find_related_channel_link", "extract", "rewrite"}:
                return ActionRisk.SAFE if not has_delivery_target else ActionRisk.SENSITIVE
        return definition.default_risk

    def _build_impact_summary(self, risk: ActionRisk, request: ActionRequest) -> str:
        target = request.target.label if request.target is not None else "current context"
        secondary = request.secondary_target.label if request.secondary_target is not None else ""
        if risk == ActionRisk.SAFE:
            return f"Read-only or draft action against {target}."
        if risk == ActionRisk.SENSITIVE:
            destination = f" and deliver to {secondary}" if secondary else ""
            return f"This will change Telegram state or send content using {target}{destination}."
        if risk == ActionRisk.DESTRUCTIVE:
            return f"This can remove or revoke data, messages, membership, or access in {target}."
        return f"This can modify critical bot or environment state related to {target}."

