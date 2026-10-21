from datetime import datetime, timedelta, timezone
from app.services.radar_engine import RadarEngine, radar_engine
from app.models.radar import UrgencyTier

def test_urgency_tier_classification():
    assert RadarEngine.classify_urgency(5.0) == UrgencyTier.PANIC
    assert RadarEngine.classify_urgency(23.9) == UrgencyTier.PANIC
    assert RadarEngine.classify_urgency(24.5) == UrgencyTier.IMMINENT
    assert RadarEngine.classify_urgency(71.9) == UrgencyTier.IMMINENT
    assert RadarEngine.classify_urgency(73.0) == UrgencyTier.UPCOMING
    assert RadarEngine.classify_urgency(-1.0) == UrgencyTier.PASSED

def test_compile_radar():
    now = datetime.now(timezone.utc)
    raw_items = [
        {
            "id": "1",
            "kind": "academic_assignment",
            "title": "Assignment 1",
            "source": "CS101",
            "deadline": now + timedelta(hours=6),
            "action_url": "https://example.com/a1"
        },
        {
            "id": "2",
            "kind": "hackathon_deadline",
            "title": "Hackathon 1",
            "source": "DEV",
            "deadline": now + timedelta(hours=48),
            "action_url": "https://example.com/h1"
        },
        {
            "id": "3",
            "kind": "academic_assignment",
            "title": "Final Project",
            "source": "CS401",
            "deadline": now + timedelta(hours=120),
            "action_url": "https://example.com/fp"
        }
    ]

    report = radar_engine.compile_radar(raw_items)
    assert report.summary.total_active == 3
    assert report.summary.panic_count == 1
    assert report.summary.imminent_count == 1
    assert report.summary.upcoming_count == 1

    # Verify chronological ordering
    assert report.items[0].id == "1"
    assert report.items[1].id == "2"
    assert report.items[2].id == "3"
