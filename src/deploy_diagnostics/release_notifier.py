from __future__ import annotations

from typing import Any, Literal, Mapping, Protocol, get_args, get_origin, get_type_hints

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # pragma: no cover - exercised only in dependency-free checks
    class _Field:
        def __init__(self, **constraints: Any) -> None:
            self.constraints = constraints

    def Field(**constraints: Any) -> Any:
        return _Field(**constraints)

    class BaseModel:
        def __init__(self, **values: Any) -> None:
            hints = get_type_hints(type(self))
            for name, annotation in hints.items():
                if name not in values:
                    raise ValueError(f"missing field: {name}")
                value = _coerce(values[name], annotation)
                default = getattr(type(self), name, None)
                if isinstance(default, _Field):
                    constraints = default.constraints
                    if "min_length" in constraints and len(value) < constraints["min_length"]:
                        raise ValueError(f"{name} is too short")
                    if "max_length" in constraints and len(value) > constraints["max_length"]:
                        raise ValueError(f"{name} is too long")
                    if "pattern" in constraints:
                        import re
                        if not re.match(constraints["pattern"], value):
                            raise ValueError(f"invalid {name}")
                setattr(self, name, value)

        @classmethod
        def model_validate(cls, value: Mapping[str, Any]) -> "BaseModel":
            return cls(**dict(value))

        def model_dump(self) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for name in get_type_hints(type(self)):
                value = getattr(self, name)
                if isinstance(value, BaseModel):
                    value = value.model_dump()
                elif isinstance(value, list):
                    value = [item.model_dump() if isinstance(item, BaseModel) else item for item in value]
                elif isinstance(value, set):
                    value = set(value)
                result[name] = value
            return result

    def _coerce(value: Any, annotation: Any) -> Any:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is Literal:
            if value not in args:
                raise ValueError(f"invalid value: {value}")
            return value
        if origin is list:
            return [_coerce(item, args[0]) for item in value]
        if origin is set:
            return {_coerce(item, args[0]) for item in value}
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.model_validate(value) if isinstance(value, Mapping) else value
        if annotation is str and not isinstance(value, str):
            raise ValueError("expected string")
        return value


class BuildEvent(BaseModel):
    build_id: str = Field(min_length=1)
    pipeline: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7)
    outcome: Literal["passed", "failed"]


class ReleaseOperation(BaseModel):
    release_id: str = Field(min_length=1)
    environment: Literal["staging", "production"]
    state: Literal["completed", "blocked"]
    diagnostic: str = Field(min_length=1, max_length=120)


class DeveloperRoute(BaseModel):
    developer_id: str = Field(min_length=1)
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    pipelines: set[str] = Field(min_length=1)
    environments: set[str] = Field(min_length=1)
    release_sms: bool


class CampaignRequest(BaseModel):
    build: BuildEvent
    release: ReleaseOperation
    routes: list[DeveloperRoute] = Field(min_length=1, max_length=100)


class MessageDiagnostic(BaseModel):
    developer_id: str
    message_id: str
    status: str


class CampaignReport(BaseModel):
    release_id: str
    eligible: int
    suppressed: int
    messages: list[MessageDiagnostic]


class SmsGateway(Protocol):
    def send(self, *, to: str, body: str, idempotency_key: str) -> Mapping[str, Any]:
        raise AssertionError("typing protocol method")

    def status(self, message_id: str) -> Mapping[str, Any]:
        raise AssertionError("typing protocol method")


class ReleaseNotifier:
    def __init__(self, sms: SmsGateway) -> None:
        self.sms = sms

    def dispatch(self, campaign: CampaignRequest) -> CampaignReport:
        eligible = [
            route
            for route in campaign.routes
            if route.release_sms
            and campaign.build.pipeline in route.pipelines
            and campaign.release.environment in route.environments
        ]
        text = (
            f"Release {campaign.release.release_id} {campaign.release.state}: "
            f"{campaign.build.pipeline} build {campaign.build.build_id} "
            f"{campaign.build.outcome}. {campaign.release.diagnostic}"
        )
        messages: list[MessageDiagnostic] = []
        for route in eligible:
            sent = self.sms.send(
                to=route.phone,
                body=text,
                idempotency_key=(
                    f"release:{campaign.release.release_id}:developer:{route.developer_id}"
                ),
            )
            message_id = str(sent["message_id"])
            current = self.sms.status(message_id)
            messages.append(
                MessageDiagnostic(
                    developer_id=route.developer_id,
                    message_id=message_id,
                    status=str(current["status"]),
                )
            )

        return CampaignReport(
            release_id=campaign.release.release_id,
            eligible=len(eligible),
            suppressed=len(campaign.routes) - len(eligible),
            messages=messages,
        )
