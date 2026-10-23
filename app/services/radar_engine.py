from datetime import datetime, timezone
from app.config import to_utc
from app.models.radar import RadarItem, UrgencyTier, RadarSummary, RadarReport, WatchlistItem

class RadarEngine:
    @staticmethod
    def classify_urgency(hours_remaining: float) -> tuple[UrgencyTier, str]:
        """
        Classifies deadlines into sloth-tailored urgency bands:
        - < 6 hours: "jaldi kar alsi, warna gaya bas {x} hours baki hai"
        - 6 to 24 hours: "abhi to {x} ghante hai :)"
        - > 24 hours: "abhi kyu karna, {x} days baki hai"
        """
        if hours_remaining < 0:
            return UrgencyTier.PASSED, "deadline nikal gaya"
        elif hours_remaining < 6.0:
            hrs = round(hours_remaining, 1)
            return UrgencyTier.CRITICAL_PANIC, f"jaldi kar alsi, warna gaya bas {hrs} hours baki hai"
        elif hours_remaining <= 24.0:
            hrs = round(hours_remaining, 1)
            return UrgencyTier.APPROACHING, f"abhi to {hrs} ghante hai :)"
        else:
            days = max(1, round(hours_remaining / 24.0))
            return UrgencyTier.CHILL, f"abhi kyu karna, {days} days baki hai"

    @classmethod
    def compile_radar(cls, raw_items: list[dict]) -> RadarReport:
        now = datetime.now(timezone.utc)
        items: list[RadarItem] = []
        watchlist_items: list[WatchlistItem] = []

        critical_count = 0
        approaching_count = 0
        chill_count = 0

        for r in raw_items:
            raw_deadline = r.get("deadline")
            has_explicit = r.get("has_explicit_deadline", True)

            # Strict Watchlist Partitioning: Items lacking verified future cutoffs go to Watchlist
            if not raw_deadline or not has_explicit:
                kind_val = "academic_task" if r.get("kind") == "academic_assignment" else "opportunity_scout"
                watchlist_items.append(
                    WatchlistItem(
                        id=r["id"],
                        kind=kind_val,
                        title=r["title"],
                        source=r["source"],
                        action_url=r.get("action_url"),
                        note=r.get("note") or "Cutoff unconfirmed — awaiting announcement",
                        account_source=r.get("account_source") or "default"
                    )
                )
                continue

            # Normalize to timezone-aware UTC via configured USER_TIMEZONE
            deadline = to_utc(raw_deadline)

            delta = deadline - now
            hours_remaining = round(delta.total_seconds() / 3600.0, 1)

            # Passed items are not active. Keeping a -1h item used to inflate
            # total_active without adding it to any of the three bands.
            if hours_remaining < 0:
                continue

            urgency, sloth_msg = cls.classify_urgency(hours_remaining)

            if urgency == UrgencyTier.CRITICAL_PANIC:
                critical_count += 1
            elif urgency == UrgencyTier.APPROACHING:
                approaching_count += 1
            elif urgency == UrgencyTier.CHILL:
                chill_count += 1

            # Priority weight calculation
            base_weight = 2.0 if r.get("kind") == "academic_assignment" else 1.0
            if urgency == UrgencyTier.CRITICAL_PANIC:
                priority_weight = base_weight * 4.0
            elif urgency == UrgencyTier.APPROACHING:
                priority_weight = base_weight * 2.0
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
                    sloth_message=sloth_msg,
                    action_url=r.get("action_url"),
                    priority_weight=priority_weight
                )
            )

        # Sort chronologically by hours remaining for live swimlanes
        items.sort(key=lambda x: x.hours_remaining)

        summary = RadarSummary(
            critical_panic_count=critical_count,
            approaching_count=approaching_count,
            chill_count=chill_count,
            total_active=len(items),
            watchlist_count=len(watchlist_items)
        )

        return RadarReport(
            timestamp=now,
            summary=summary,
            items=items,
            watchlist=watchlist_items
        )

radar_engine = RadarEngine()
