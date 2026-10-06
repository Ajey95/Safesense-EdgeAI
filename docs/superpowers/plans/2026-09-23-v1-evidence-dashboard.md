# V1 Evidence Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the updated V2 dashboard experience into V1 while displaying stored JSON and only verifiable communication evidence.

**Architecture:** Port the V2 view-model and Streamlit layout selectively; extend the V1 overview response with persisted event metadata. Backend HTTP receipt is an observed hop; device origin and TX-to-RX remain unverified until physical evidence exists.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Streamlit, pytest, browser screenshot review.

**Spec:** `docs/superpowers/specs/2026-09-23-v1-tx-and-evidence-dashboard-design.md`

## Global Constraints

- Stay on `v1` and preserve the current humidity-display edit in `dashboard/app.py`.
- Never port V2 hard-coded `HOST VERIFIED` badges or firmware-name-based device-origin inference.
- Preserve Environment, Wi-Fi CSI, Human Context, System, and Recent Events.
- Unknown/stale evidence remains `UNKNOWN` or `UNAVAILABLE`.

## Review Focus

- A simulation POST and a physical POST both use HTTP: neither earns a device-origin badge; Task 2 test.
- An old event is still stored but not current: show stale status; Task 2 test.
- JSON includes HTML/script text: render safely, never inject it; Task 2 test.
- No event exists: show waiting, not connected/live; Task 2 test.
- Duplicate event ID: stored event remains one record and the dashboard shows its real ID/time; Task 1 test.

---

### Task 1: Backend event evidence

**Files:** Modify `src/safesense/main.py`; extend `tests/test_api.py`.

**Interfaces:** `/api/v1/overview` telemetry rows add `event_id`, `received_at`, and `backend_ingress="HTTP POST"` alongside persisted `payload`.

- [ ] Write a failing API test that POSTs a literal event, then checks overview for the same event ID, stored JSON, server receipt time, and HTTP ingress label.
- [ ] Run `python -m pytest tests/test_api.py -q` and confirm the new assertions fail.
- [ ] Extend the overview projection from stored `TelemetryEvent` fields; rerun the focused tests green.

### Task 2: V2 layout with truthful evidence

**Files:** Create `src/safesense/dashboard_view.py` from a selective V2 port; modify `dashboard/app.py`; add `tests/test_dashboard_view.py`.

**Interfaces:** `build_dashboard_view(latest, now=...)` returns five existing sections plus an evidence section containing backend HTTP receipt and unverified device-hop status; Streamlit shows `st.json(latest["payload"])` in an expander.

- [ ] Write failing view-model tests for stale values, unverified origin, no hard-coded verification, event ID, and escaped malicious text.
- [ ] Run `python -m pytest tests/test_dashboard_view.py -q` and confirm the expected failures.
- [ ] Port the V2 layout/view-model with only source-backed statuses; preserve the V1 humidity fix and remove MQTT-only claims.
- [ ] Run the focused tests, then `python -m pytest -q`.
- [ ] Start FastAPI and Streamlit, inspect desktop and narrow screenshots in light and dark themes, and confirm JSON/evidence display matches a stored API event.
