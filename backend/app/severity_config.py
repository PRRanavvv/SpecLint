from __future__ import annotations

from dataclasses import dataclass

from .models import IssueType, ProjectDomain, RiskOverlay, Severity


@dataclass(frozen=True)
class SeverityCalibration:
    multiplier: float = 1.0
    reason: str = ""


DOMAIN_SEVERITY_CONFIG: dict[ProjectDomain, dict[IssueType, SeverityCalibration]] = {
    ProjectDomain.general: {},
    ProjectDomain.fintech: {
        IssueType.permission_gap: SeverityCalibration(1.35, "Elevated for fintech risk profile."),
        IssueType.consent_gap: SeverityCalibration(1.3, "Elevated for fintech risk profile."),
        IssueType.data_constraint_gap: SeverityCalibration(1.35, "Elevated for fintech risk profile."),
        IssueType.lifecycle_gap: SeverityCalibration(1.2, "Elevated for fintech risk profile."),
        IssueType.failure_mode_gap: SeverityCalibration(1.2, "Elevated for fintech risk profile."),
    },
    ProjectDomain.health: {
        IssueType.permission_gap: SeverityCalibration(1.35, "Elevated for health data risk."),
        IssueType.consent_gap: SeverityCalibration(1.35, "Elevated for health data risk."),
        IssueType.data_constraint_gap: SeverityCalibration(1.35, "Elevated for health data risk."),
        IssueType.failure_mode_gap: SeverityCalibration(1.25, "Elevated for health data risk."),
    },
    ProjectDomain.ecommerce: {
        IssueType.permission_gap: SeverityCalibration(1.2, "Elevated for e-commerce transaction risk."),
        IssueType.data_constraint_gap: SeverityCalibration(1.2, "Elevated for e-commerce transaction risk."),
        IssueType.lifecycle_gap: SeverityCalibration(1.2, "Elevated for e-commerce transaction risk."),
        IssueType.failure_mode_gap: SeverityCalibration(1.15, "Elevated for e-commerce transaction risk."),
    },
    ProjectDomain.internal_tooling: {
        IssueType.unverifiable_claim: SeverityCalibration(0.7, "Softened for internal tooling domain."),
        IssueType.ambiguity: SeverityCalibration(0.85, "Softened for internal tooling domain."),
        IssueType.failure_mode_gap: SeverityCalibration(0.85, "Softened for internal tooling domain."),
    },
}

OVERLAY_SEVERITY_CONFIG: dict[RiskOverlay, dict[IssueType, SeverityCalibration]] = {
    RiskOverlay.auth: {
        IssueType.permission_gap: SeverityCalibration(1.4, "Elevated because this spec handles auth."),
        IssueType.consent_gap: SeverityCalibration(1.25, "Elevated because this spec handles auth."),
        IssueType.failure_mode_gap: SeverityCalibration(1.25, "Elevated because this spec handles auth."),
        IssueType.lifecycle_gap: SeverityCalibration(1.15, "Elevated because this spec handles auth."),
    },
    RiskOverlay.payments: {
        IssueType.permission_gap: SeverityCalibration(1.4, "Elevated because this spec handles payments."),
        IssueType.consent_gap: SeverityCalibration(1.25, "Elevated because this spec handles payments."),
        IssueType.data_constraint_gap: SeverityCalibration(1.35, "Elevated because this spec handles payments."),
        IssueType.lifecycle_gap: SeverityCalibration(1.25, "Elevated because this spec handles payments."),
        IssueType.failure_mode_gap: SeverityCalibration(1.25, "Elevated because this spec handles payments."),
    },
    RiskOverlay.pii: {
        IssueType.permission_gap: SeverityCalibration(1.35, "Elevated because this spec handles PII."),
        IssueType.consent_gap: SeverityCalibration(1.25, "Elevated because this spec handles PII."),
        IssueType.data_constraint_gap: SeverityCalibration(1.4, "Elevated because this spec handles PII."),
    },
    RiskOverlay.public_sharing: {
        IssueType.permission_gap: SeverityCalibration(1.3, "Elevated because this spec has public sharing."),
        IssueType.lifecycle_gap: SeverityCalibration(1.25, "Elevated because this spec has public sharing."),
        IssueType.failure_mode_gap: SeverityCalibration(1.2, "Elevated because this spec has public sharing."),
    },
    RiskOverlay.high_availability: {
        IssueType.failure_mode_gap: SeverityCalibration(1.4, "Elevated because this spec needs high availability."),
        IssueType.lifecycle_gap: SeverityCalibration(1.2, "Elevated because this spec needs high availability."),
        IssueType.data_constraint_gap: SeverityCalibration(1.15, "Elevated because this spec needs high availability."),
    },
}

SEVERITY_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]


def calibration_for(
    issue_type: IssueType,
    domain: ProjectDomain,
    overlays: list[RiskOverlay],
) -> SeverityCalibration:
    candidates = [
        DOMAIN_SEVERITY_CONFIG.get(domain, {}).get(issue_type, SeverityCalibration()),
        *(
            OVERLAY_SEVERITY_CONFIG.get(overlay, {}).get(issue_type, SeverityCalibration())
            for overlay in overlays
        ),
    ]
    elevations = [candidate for candidate in candidates if candidate.multiplier > 1]
    if elevations:
        return max(elevations, key=lambda candidate: candidate.multiplier)
    softeners = [candidate for candidate in candidates if candidate.multiplier < 1]
    if softeners:
        return min(softeners, key=lambda candidate: candidate.multiplier)
    return SeverityCalibration()


def adjusted_severity(severity: Severity, multiplier: float) -> Severity:
    if multiplier >= 1.2:
        return _shift(severity, 1)
    if multiplier <= 0.8:
        return _shift(severity, -1)
    return severity


def domain_note(domain: ProjectDomain, overlays: list[RiskOverlay]) -> str:
    domain_label = domain.value.replace("_", " ")
    if overlays:
        overlay_labels = ", ".join(overlay.value.replace("_", " ") for overlay in overlays)
        return f"Domain: {domain_label}. Risk overlays: {overlay_labels}."
    return f"Domain: {domain_label}. No risk overlays selected."


def _shift(severity: Severity, steps: int) -> Severity:
    index = SEVERITY_ORDER.index(severity)
    next_index = max(0, min(len(SEVERITY_ORDER) - 1, index + steps))
    return SEVERITY_ORDER[next_index]
