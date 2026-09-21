from .schemas import FusionResult, FusionState, HumanContext, Risk, TelemetryIn

MINIMUM_CSI_CONFIDENCE = 0.70


def evaluate(telemetry: TelemetryIn) -> FusionResult:
    """Safety policy is deterministic; CSI can add context but cannot erase danger."""
    env = telemetry.environment
    csi = telemetry.csi
    context_known = csi.is_fresh and csi.activity.value != "UNKNOWN" and csi.confidence >= MINIMUM_CSI_CONFIDENCE
    if env.gas_risk == Risk.CRITICAL:
        return FusionResult(state=FusionState.INCIDENT, reason="Critical environmental risk; CSI cannot suppress the incident.", reason_code="ENVIRONMENT_CRITICAL", human_context=HumanContext.KNOWN if context_known else HumanContext.UNKNOWN, local_alarm=True, incident_required=True)
    if not env.sensor_healthy or env.gas_risk == Risk.UNAVAILABLE:
        return FusionResult(state=FusionState.DEGRADED, reason="Environmental sensor health is degraded; safe conditions cannot be confirmed.", reason_code="ENVIRONMENT_UNAVAILABLE", human_context=HumanContext.UNKNOWN, local_alarm=False, incident_required=False)
    if env.gas_risk == Risk.WARNING:
        return FusionResult(state=FusionState.WARNING, reason="Environmental warning requires attention.", reason_code="ENVIRONMENT_WARNING", human_context=HumanContext.KNOWN if context_known else HumanContext.UNKNOWN, local_alarm=False, incident_required=False)
    if not csi.is_fresh:
        return FusionResult(state=FusionState.DEGRADED, reason="Environment normal; CSI is stale.", reason_code="CSI_STALE", human_context=HumanContext.UNKNOWN, local_alarm=False, incident_required=False)
    if csi.activity.value == "UNKNOWN" or csi.confidence < MINIMUM_CSI_CONFIDENCE:
        return FusionResult(state=FusionState.DEGRADED, reason="Environment normal; CSI activity is uncertain.", reason_code="CSI_UNCERTAIN", human_context=HumanContext.UNKNOWN, local_alarm=False, incident_required=False)
    return FusionResult(state=FusionState.NORMAL, reason=f"Environment normal; activity {csi.activity}.", reason_code="ALL_SIGNALS_NOMINAL", human_context=HumanContext.KNOWN, local_alarm=False, incident_required=False)
