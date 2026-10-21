from datetime import datetime, timezone
from app.models.radar import RadarItem, UrgencyTier, RadarSummary, RadarReport

class RadarEngine:
    @staticmethod
    def classify_urgency(hours_remaining: float) -> UrgencyTier:
        if hours_remaining < 0:
            return UrgencyTier.PASSED
        elif hours_remaining <= 24.0:
            return UrgencyTier.PANIC
        elif hours_remaining <= 72.0:
            return UrgencyTier.IMMINENT
        else:
            return UrgencyTier.UPCOMING

    @classmethod
    def compile_radar(cls, raw_items: list[dict]) -> RadarReport:
        now = datetime.now(timezone.utc)
        items: list[RadarItem] = []

        panic_count = 0
        imminent_count = 0
        upcoming_count = 0

        for r in raw_items:
            deadline = r["deadline"]
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)

            delta = deadline - now
            hours_remaining = round(delta.total_seconds() / 3600.0, 1)

            # Skip already passed deadlines if older than 2 hours
            if hours_remaining < -2.0:
                continue

            urgency = cls.classify_urgency(hours_remaining)

            if urgency == UrgencyTier.PANIC:
                panic_count += 1
            elif urgency == UrgencyTier.IMMINENT:
                imminent_count += 1
            elif urgency == UrgencyTier.UPCOMING:
                upcoming_count += 1

            # Priority weight calculation
            base_weight = 2.0 if r.get("kind") == "academic_assignment" else 1.0
            if urgency == UrgencyTier.PANIC:
                priority_weight = base_weight * 3.0
            elif urgency == UrgencyTier.IMMINENT:
                priority_weight = base_weight * 1.5
            else:
                priority_weight = base_weight

            items.append(
                RadarItem(
                    id=r["id"],
                    kind=r["kind"],
                    title=r["title"],
                    source=r["source"],
                    deadline=deadline,
                    hours_remaining=hours_remaining,
                    urgency=urgency,
                    action_url=r.get("action_url"),
                    priority_weight=priority_weight
                )
            )

        # Sort chronologically by hours remaining
        items.sort(key=lambda x: x.hours_remaining)

        summary = RadarSummary(
            panic_count=panic_count,
            imminent_count=imminent_count,
            upcoming_count=upcoming_count,
            total_active=len(items)
        )

        return RadarReport(
            timestamp=now,
            summary=summary,
            items=items
        )

radar_engine = RadarEngine()
