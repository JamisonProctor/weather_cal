from types import SimpleNamespace

from icalendar import Calendar

from src.events.ics_events import build_event_ics


def _parse_events(ics_bytes: bytes) -> list:
    cal = Calendar.from_ical(ics_bytes)
    return [c for c in cal.walk() if c.name == "VEVENT"]


def _make_event(**overrides):
    defaults = dict(
        id="test-uuid-1",
        title="Open Air Concert",
        start_time="2026-03-15T18:00:00+01:00",
        end_time="2026-03-15T21:00:00+01:00",
        location="Olympiapark, Munich",
        description="Free concert in the park",
        source_url="https://example.com/concert",
        external_key="abc123def456",
        category="concert",
        is_paid=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_event_ics_single_event():
    event = _make_event()
    ics_bytes = build_event_ics([event])
    events = _parse_events(ics_bytes)
    assert len(events) == 1
    assert str(events[0]["SUMMARY"]) == "Open Air Concert"
    assert str(events[0]["LOCATION"]) == "Olympiapark, Munich"
    assert str(events[0]["URL"]) == "https://example.com/concert"


def test_build_event_ics_stable_uid():
    event = _make_event()
    ics1 = build_event_ics([event])
    ics2 = build_event_ics([event])
    events1 = _parse_events(ics1)
    events2 = _parse_events(ics2)
    assert str(events1[0]["UID"]) == str(events2[0]["UID"])
    assert str(events1[0]["UID"]).endswith("@planz")


def test_build_event_ics_uid_uses_external_key():
    e1 = _make_event(external_key="key_a")
    e2 = _make_event(external_key="key_b")
    events1 = _parse_events(build_event_ics([e1]))
    events2 = _parse_events(build_event_ics([e2]))
    assert str(events1[0]["UID"]) != str(events2[0]["UID"])


def test_build_event_ics_opaque_transp():
    event = _make_event()
    events = _parse_events(build_event_ics([event]))
    assert str(events[0]["TRANSP"]) == "OPAQUE"


def test_build_event_ics_empty_list():
    ics_bytes = build_event_ics([])
    cal = Calendar.from_ical(ics_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 0
    assert b"VCALENDAR" in ics_bytes


def test_build_event_ics_cal_name():
    ics_bytes = build_event_ics([], cal_name="Test Events")
    assert b"Test Events" in ics_bytes


def test_build_event_ics_prodid():
    ics_bytes = build_event_ics([])
    assert b"PLANZ" in ics_bytes


def test_build_event_ics_refresh_interval():
    ics_bytes = build_event_ics([])
    assert b"PT6H" in ics_bytes


def test_build_event_ics_description():
    event = _make_event(description="A great event with live music")
    events = _parse_events(build_event_ics([event]))
    assert "live music" in str(events[0]["DESCRIPTION"])


def test_build_event_ics_multiple_events():
    e1 = _make_event(external_key="key1", title="Event One")
    e2 = _make_event(external_key="key2", title="Event Two")
    events = _parse_events(build_event_ics([e1, e2]))
    assert len(events) == 2
    titles = {str(e["SUMMARY"]) for e in events}
    assert titles == {"Event One", "Event Two"}


def test_build_event_ics_no_external_key_uses_id():
    event = _make_event(external_key=None, id="fallback-uuid")
    events = _parse_events(build_event_ics([event]))
    uid = str(events[0]["UID"])
    assert uid.endswith("@planz")
