from datetime import datetime, timedelta, timezone
from app.services.radar_engine import RadarEngine, radar_engine
from app.models.radar import UrgencyTier

def test_urgency_tier_classification():
    # < 6h: critical panic
    tier, msg = RadarEngine.classify_urgency(3.5)
    assert tier == UrgencyTier.CRITICAL_PANIC
    assert "jaldi kar alsi, warna gaya bas 3.5 hours baki hai" == msg

    tier, msg = RadarEngine.classify_urgency(5.9)
    assert tier == UrgencyTier.CRITICAL_PANIC

    # 6h - 24h: approaching
    tier, msg = RadarEngine.classify_urgency(12.0)
    assert tier == UrgencyTier.APPROACHING
    assert "abhi to 12.0 ghante hai :)" == msg

    tier, msg = RadarEngine.classify_urgency(24.0)
    assert tier == UrgencyTier.APPROACHING

    # > 24h: chill
    tier, msg = RadarEngine.classify_urgency(48.0)
    assert tier == UrgencyTier.CHILL
    assert "abhi kyu karna, 2 days baki hai" == msg

    tier, msg = RadarEngine.classify_urgency(96.0)
    assert tier == UrgencyTier.CHILL
    assert "abhi kyu karna, 4 days baki hai" == msg

    # Passed
    tier, msg = RadarEngine.classify_urgency(-1.0)
    assert tier == UrgencyTier.PASSED
    assert "deadline nikal gaya" == msg

def test_compile_radar():
    now = datetime.now(timezone.utc)
    raw_items = [
        {
            "id": "1",
            "kind": "academic_assignment",
            "title": "Assignment 1",
            "source": "CS101",
            "deadline": now + timedelta(hours=3),
            "action_url": "https://example.com/a1"
        },
        {
            "id": "2",
            "kind": "hackathon_deadline",
            "title": "Hackathon 1",
            "source": "DEV",
            "deadline": now + timedelta(hours=18),
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
    assert report.summary.critical_panic_count == 1
    assert report.summary.approaching_count == 1
    assert report.summary.chill_count == 1

    # Verify chronological ordering
    assert report.items[0].id == "1"
    assert report.items[0].urgency == UrgencyTier.CRITICAL_PANIC
    assert "jaldi kar alsi" in report.items[0].sloth_message

    assert report.items[1].id == "2"
    assert report.items[1].urgency == UrgencyTier.APPROACHING
    assert "abhi to" in report.items[1].sloth_message

    assert report.items[2].id == "3"
    assert report.items[2].urgency == UrgencyTier.CHILL
    assert "abhi kyu karna" in report.items[2].sloth_message
