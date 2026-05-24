import atexit
import random
from datetime import datetime, timedelta

from app.extensions import db


def _base_traffic_count_for_hour(hour):
    if 0 <= hour <= 9:
        return random.randint(50, 100)
    if hour == 10:
        return random.randint(150, 250)
    if hour == 11:
        return random.randint(300, 450)
    if hour == 12:
        return random.randint(500, 700)
    if hour == 13:
        return random.randint(700, 900)
    if hour == 14:
        return random.randint(600, 750)
    if hour == 15:
        return random.randint(450, 600)
    if hour == 16:
        return random.randint(500, 650)
    if hour == 17:
        return random.randint(650, 800)
    if hour == 18:
        return random.randint(800, 1000)
    if hour == 19:
        return random.randint(900, 1100)
    if hour == 20:
        return random.randint(850, 1050)
    if hour == 21:
        return random.randint(600, 800)
    if hour == 22:
        return random.randint(250, 400)
    return random.randint(50, 100)


def _zone_multiplier(zone, hour):
    if zone == "A":
        return 1.1
    if zone == "B":
        return 0.9
    if zone == "C":
        return 0.85
    if zone == "D":
        return 1.3 if 12 <= hour <= 14 else 1.15
    return 1.0


def simulate_foot_traffic(app):
    with app.app_context():
        try:
            from app.models.inventory import FootTraffic
            from app.models.property import MallProperty

            properties = MallProperty.query.filter_by(onboarding_complete=True).all()
            zones = ["A", "B", "C", "D", "E"]
            now_local = datetime.now()
            now_utc = datetime.utcnow()
            hour = now_local.hour
            weekday = now_local.weekday()
            weekend_multiplier = 1.4 if weekday >= 5 else 1.0

            for property_record in properties:
                base_count = _base_traffic_count_for_hour(hour)
                new_records = []

                for zone in zones:
                    zone_multiplier = _zone_multiplier(zone, hour)
                    random_variance = random.uniform(0.9, 1.1)
                    calculated_count = int(
                        base_count * weekend_multiplier * zone_multiplier * random_variance
                    )
                    calculated_count = max(calculated_count, 10)

                    new_records.append(
                        FootTraffic(
                            property_id=property_record.id,
                            zone_id=zone,
                            floor=1,
                            count=calculated_count,
                            timestamp=now_utc,
                            data_source="simulator",
                        )
                    )

                db.session.add_all(new_records)
                db.session.commit()

                cutoff = datetime.utcnow() - timedelta(days=7)
                FootTraffic.query.filter(
                    FootTraffic.property_id == property_record.id,
                    FootTraffic.timestamp < cutoff,
                ).delete(synchronize_session=False)
                db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Foot traffic simulator job failed")


def init_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.services.agent_runner import (
        cleanup_expired_tokens,
        run_campaign_cos_job,
        run_facility_fps_job,
        run_inventory_srs_job,
        send_daily_briefing,
        simulate_sensor_readings,
    )

    existing_scheduler = getattr(app, "scheduler", None)
    if existing_scheduler is not None:
        if not existing_scheduler.running:
            existing_scheduler.start()
        return existing_scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        simulate_foot_traffic,
        trigger="interval",
        minutes=5,
        args=[app],
        id="foot_traffic_simulator",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_inventory_srs_job,
        trigger="interval",
        minutes=15,
        args=[app],
        id="inventory_srs_runner",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_campaign_cos_job,
        trigger="interval",
        minutes=30,
        args=[app],
        id="campaign_cos_runner",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        simulate_sensor_readings,
        trigger="interval",
        minutes=5,
        args=[app],
        id="sensor_reading_simulator",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_facility_fps_job,
        trigger="interval",
        minutes=10,
        args=[app],
        id="facility_fps_runner",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_daily_briefing,
        trigger="cron",
        hour=8,
        minute=0,
        args=[app],
        id="daily_notification_briefing",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        cleanup_expired_tokens,
        trigger="cron",
        hour=2,
        minute=0,
        args=[app],
        id="token_cleanup_runner",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    if not scheduler.running:
        scheduler.start()

    app.scheduler = scheduler

    def shutdown_scheduler():
        if scheduler.running:
            scheduler.shutdown(wait=False)

    atexit.register(shutdown_scheduler)
