from datetime import datetime, timedelta
import random


def run_inventory_mission(app, property_id=None):
    from app.extensions import db

    with app.app_context():
        from app.models.agent import AgentAction, AgentConfiguration
        from app.models.inventory import InventoryItem
        from app.models.property import MallProperty
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.services.inventory_service import compute_srs_for_sku
        from app.services.notification_service import create_notification

        try:
            if property_id is not None:
                properties = MallProperty.query.filter_by(id=property_id, onboarding_complete=True).all()
            else:
                properties = MallProperty.query.filter_by(onboarding_complete=True).all()

            for property_record in properties:
                prop_id = property_record.id
                agent_config = AgentConfiguration.query.filter_by(property_id=prop_id).first()
                if agent_config is None:
                    continue
                if not agent_config.inventory_mission_enabled:
                    continue

                inventory_items = InventoryItem.query.filter_by(property_id=prop_id).all()
                alerts_created = 0

                for inventory_item in inventory_items:
                    try:
                        srs_result = compute_srs_for_sku(
                            inventory_item.sku_id,
                            prop_id,
                            inventory_item.tenant_id,
                        )
                        srs_score = float(srs_result.get("srs_score") or 0.0)

                        if srs_score <= float(agent_config.inventory_srs_threshold or 0.70):
                            continue

                        existing = AgentAction.query.filter_by(
                            property_id=prop_id,
                            entity_id=inventory_item.sku_id,
                            mission_type="inventory",
                            status="pending",
                        ).first()
                        if existing is not None:
                            continue

                        tenant = Tenant.query.filter_by(
                            id=inventory_item.tenant_id,
                            property_id=prop_id,
                        ).first()

                        restock_qty = max(50, int((inventory_item.reorder_threshold or 0) * 3))
                        fallback_reasoning = (
                            f"Stock level of {inventory_item.stock_level} units is critically low relative to the reorder "
                            f"threshold of {inventory_item.reorder_threshold}. With current sales velocity, stockout is "
                            f"imminent. Recommend immediate restock of {restock_qty} units from "
                            f"{inventory_item.supplier_name or 'primary supplier'}."
                        )

                        gemini_reasoning_text = fallback_reasoning
                        reasoning_prompt = (
                            "You are an AI agent monitoring mall inventory. Explain in 2-3 sentences why this "
                            "product needs restocking and what the store manager should do:\n"
                            f"Product: {inventory_item.product_name} | Brand: {inventory_item.brand}\n"
                            f"Store: {(tenant.name if tenant else 'Unknown Store')} | Zone: {(tenant.zone if tenant else 'Unknown')}\n"
                            f"Current Stock: {inventory_item.stock_level} units\n"
                            f"Reorder Threshold: {inventory_item.reorder_threshold} units\n"
                            f"SRS Score: {srs_score:.2f}/1.00 (threshold: {agent_config.inventory_srs_threshold})\n"
                            f"Time to Stockout: {srs_result.get('tts_hours', 'Unknown')} hours\n"
                            f"Recent Sales Velocity: {srs_result.get('sales_velocity_2h', 0)} units in last 2 hours\n"
                            f"Supplier: {inventory_item.supplier_name} (Lead time: {inventory_item.supplier_lead_time_hours} hours)\n"
                            f"Recommended restock quantity: {restock_qty} units"
                        )

                        if app.config.get("GEMINI_ENABLED", False):
                            try:
                                from google import genai

                                client = genai.Client()
                                response = client.models.generate_content(
                                    model="gemini-2.5-flash",
                                    contents=reasoning_prompt,
                                )
                                result_text = response.text
                                if result_text and result_text.strip():
                                    gemini_reasoning_text = result_text.strip()
                            except Exception:
                                app.logger.exception(
                                    "Gemini inventory reasoning failed for sku_id=%s property_id=%s",
                                    inventory_item.sku_id,
                                    prop_id,
                                )
                                gemini_reasoning_text = fallback_reasoning

                        action_description = (
                            f"Restock recommended: {inventory_item.product_name} ({inventory_item.sku_id}) in "
                            f"{tenant.name if tenant else 'Unknown Tenant'}. Stock: "
                            f"{inventory_item.stock_level}/{inventory_item.reorder_threshold}. "
                            f"SRS: {srs_score:.2f}"
                        )

                        new_action = AgentAction(
                            mission_type="inventory",
                            action_type="restock_request",
                            description=action_description,
                            entity_id=inventory_item.sku_id,
                            score=srs_score,
                            status="pending",
                            agent_reasoning=gemini_reasoning_text,
                            property_id=prop_id,
                            created_at=datetime.utcnow(),
                        )
                        db.session.add(new_action)
                        db.session.commit()

                        if agent_config.auto_approve_restock:
                            new_action.status = "auto_executed"
                            new_action.resolved_at = datetime.utcnow()
                            db.session.commit()

                        recipients = User.query.filter(
                            User.property_id == prop_id,
                            User.role.in_(["mall_admin", "store_manager"]),
                        ).all()

                        for user in recipients:
                            push_payload = None
                            if srs_score > 0.85:
                                push_payload = {
                                    "title": "Critical Restock Alert",
                                    "body": (
                                        f"{inventory_item.product_name} in "
                                        f"{tenant.name if tenant else 'tenant'} stock critically low"
                                    ),
                                    "icon": "/static/icons/icon-192.png",
                                    "badge": "/static/icons/icon-72.png",
                                    "tag": f"inventory-alert-{inventory_item.sku_id}",
                                    "data": {"url": f"/inventory/{inventory_item.sku_id}"},
                                    "actions": [
                                        {"action": "approve", "title": "Approve Restock"},
                                        {"action": "view", "title": "View Details"},
                                    ],
                                    "vibrate": [200, 100, 200],
                                    "requireInteraction": True,
                                }
                            create_notification(
                                user_id=user.id,
                                title=f"\u26a0\ufe0f Restock Alert: {inventory_item.product_name}",
                                message=(
                                    f"SRS Score {srs_score:.2f} - {inventory_item.product_name} in "
                                    f"{tenant.name if tenant else 'a tenant'} needs restocking."
                                ),
                                notification_type="inventory_alert",
                                severity="critical" if srs_score > 0.85 else "warning",
                                action_url=f"/inventory/{inventory_item.sku_id}",
                                property_id=prop_id,
                                push_payload=push_payload,
                            )

                            if agent_config.auto_approve_restock:
                                create_notification(
                                    user_id=user.id,
                                    title="Agent action auto executed",
                                    message=(
                                        f"Restock action {new_action.id} was executed automatically."
                                    ),
                                    notification_type="agent_action",
                                    severity="info",
                                    action_url=f"/inventory/{inventory_item.sku_id}",
                                    property_id=prop_id,
                                    push_payload={
                                        "title": "Agent Action Completed",
                                        "body": (
                                            f"Restock auto executed for {inventory_item.product_name}"
                                        ),
                                        "icon": "/static/icons/icon-192.png",
                                        "badge": "/static/icons/icon-72.png",
                                        "tag": f"agent-action-{new_action.id}",
                                        "data": {"url": f"/inventory/{inventory_item.sku_id}"},
                                        "vibrate": [150, 100, 150],
                                        "requireInteraction": False,
                                    },
                                )

                        alerts_created += 1
                    except Exception:
                        db.session.rollback()
                        app.logger.exception(
                            "Inventory mission failed for sku_id=%s property_id=%s",
                            inventory_item.sku_id,
                            prop_id,
                        )

                print(
                    f"[Inventory Mission] Property {prop_id}: Checked {len(inventory_items)} SKUs, "
                    f"{alerts_created} alerts created."
                )
        except Exception:
            db.session.rollback()
            app.logger.exception("Inventory mission failed")


def run_campaign_mission(app, property_id=None):
    from app.extensions import db

    with app.app_context():
        from app.models.agent import AgentAction, AgentConfiguration
        from app.models.campaign import Campaign
        from app.models.property import MallProperty
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.services.campaign_service import compute_cos_for_tenant_zone, generate_campaign_copy
        from app.services.notification_service import create_notification

        try:
            if property_id is not None:
                properties = MallProperty.query.filter_by(id=property_id, onboarding_complete=True).all()
            else:
                properties = MallProperty.query.filter_by(onboarding_complete=True).all()

            for property_record in properties:
                prop_id = property_record.id
                agent_config = AgentConfiguration.query.filter_by(property_id=prop_id).first()
                if agent_config is None or not agent_config.campaign_mission_enabled:
                    continue

                tenants = Tenant.query.filter_by(property_id=prop_id, is_active=True).all()
                opportunities_created = 0

                for tenant in tenants:
                    try:
                        cos_result = compute_cos_for_tenant_zone(
                            tenant.id,
                            tenant.zone,
                            prop_id,
                        )
                        cos_score = float(cos_result.get("cos_score") or 0.0)

                        if cos_score <= float(agent_config.campaign_cos_threshold or 0.75):
                            continue

                        existing_campaign = Campaign.query.filter(
                            Campaign.tenant_id == tenant.id,
                            Campaign.property_id == prop_id,
                            Campaign.status.in_(["opportunity", "pending_activation", "active"]),
                        ).first()
                        if existing_campaign is not None:
                            continue

                        existing_action = AgentAction.query.filter_by(
                            entity_id=str(tenant.id),
                            mission_type="campaign",
                            property_id=prop_id,
                            status="pending",
                        ).first()
                        if existing_action is not None:
                            continue

                        copy_result = generate_campaign_copy(
                            tenant,
                            tenant.zone,
                            cos_result,
                            property_record.city or "India",
                        )

                        new_campaign = Campaign(
                            property_id=prop_id,
                            tenant_id=tenant.id,
                            campaign_name=copy_result["campaign_name"],
                            campaign_copy=copy_result["campaign_copy"],
                            target_zone=tenant.zone,
                            target_audience_description=copy_result["target_audience_description"],
                            opportunity_score=cos_score,
                            status="opportunity",
                            channel=copy_result["recommended_channel"],
                            weather_context=cos_result.get("weather_context", ""),
                            event_context=cos_result.get("event_context", ""),
                            created_by_agent=True,
                            gemini_prompt_used=(
                                f"COS factors: TF={cos_result.get('tf', 0):.2f} "
                                f"TP={cos_result.get('tp', 0):.2f} "
                                f"WM={cos_result.get('wm', 0):.2f} "
                                f"EM={cos_result.get('em', 0):.2f} "
                                f"LP={cos_result.get('lp', 0):.2f}"
                            ),
                        )
                        db.session.add(new_campaign)
                        db.session.flush()

                        new_action = AgentAction(
                            property_id=prop_id,
                            mission_type="campaign",
                            action_type="campaign_opportunity",
                            description=(
                                f"Campaign opportunity: {copy_result['campaign_name']} for {tenant.name} in "
                                f"Zone {tenant.zone}. COS: {cos_score:.2f}"
                            ),
                            entity_id=str(tenant.id),
                            score=cos_score,
                            status="pending",
                            agent_reasoning=(
                                f"COS analysis for {tenant.name}: Traffic Factor={cos_result.get('tf', 0):.2f}, "
                                f"Weather Match={cos_result.get('wm', 0):.2f}, "
                                f"Event Proximity={cos_result.get('em', 0):.2f}. "
                                f"Overall opportunity score {cos_score:.2f} exceeds threshold "
                                f"{agent_config.campaign_cos_threshold}."
                            ),
                        )
                        db.session.add(new_action)
                        db.session.commit()

                        auto_activated = False
                        if agent_config.auto_approve_campaigns:
                            new_campaign.status = "active"
                            new_campaign.activated_at = datetime.utcnow()
                            new_action.status = "auto_executed"
                            new_action.resolved_at = datetime.utcnow()
                            db.session.commit()
                            auto_activated = True

                        recipients = User.query.filter(
                            User.property_id == prop_id,
                            User.role.in_(["mall_admin", "marketing_manager"]),
                        ).all()

                        for user in recipients:
                            create_notification(
                                user_id=user.id,
                                title=f"\U0001F4E3 Campaign Opportunity: {tenant.name}",
                                message=(
                                    f"COS {cos_score:.2f} - {copy_result['campaign_name']} for Zone {tenant.zone}"
                                ),
                                notification_type="campaign_opportunity",
                                severity="info",
                                action_url=f"/campaigns/{new_campaign.id}",
                                property_id=prop_id,
                            )

                            if auto_activated:
                                create_notification(
                                    user_id=user.id,
                                    title="Campaign activated",
                                    message=(
                                        f"{new_campaign.campaign_name} is now live for Zone {tenant.zone}."
                                    ),
                                    notification_type="campaign_opportunity",
                                    severity="success",
                                    action_url=f"/campaigns/{new_campaign.id}",
                                    property_id=prop_id,
                                    push_payload={
                                        "title": "Campaign Activated",
                                        "body": (
                                            f"{new_campaign.campaign_name} is now live for Zone {tenant.zone}."
                                        ),
                                        "icon": "/static/icons/icon-192.png",
                                        "badge": "/static/icons/icon-72.png",
                                        "tag": f"campaign-activated-{new_campaign.id}",
                                        "data": {"url": f"/campaigns/{new_campaign.id}"},
                                        "vibrate": [120, 80, 120],
                                        "requireInteraction": False,
                                    },
                                )

                        opportunities_created += 1
                    except Exception:
                        db.session.rollback()
                        app.logger.exception(
                            "Campaign mission failed for tenant_id=%s property_id=%s",
                            tenant.id,
                            prop_id,
                        )

                print(
                    f"[Campaign Mission] Property {prop_id}: Checked {len(tenants)} tenants, "
                    f"{opportunities_created} opportunities created."
                )
        except Exception:
            db.session.rollback()
            app.logger.exception("Campaign mission failed")


def run_inventory_srs_job(app):
    try:
        with app.app_context():
            run_inventory_mission(app)
    except Exception as e:
        print(f"[Inventory SRS Job Error] {e}")


def run_campaign_cos_job(app):
    try:
        with app.app_context():
            run_campaign_mission(app)
    except Exception as e:
        print(f"[Campaign COS Job Error] {e}")


def _facility_primary_metric(equipment_type):
    mapping = {
        "escalator": "vibration_hz",
        "elevator": "vibration_hz",
        "hvac": "temperature_celsius",
        "generator": "current_amps",
        "fire_alarm": "current_amps",
        "restroom_sensor": "occupancy_count",
        "parking_sensor": "occupancy_count",
        "food_court_exhaust": "temperature_celsius",
    }
    return mapping.get((equipment_type or "").strip().lower(), "vibration_hz")


def _sensor_range(equipment):
    equipment_type = (equipment.equipment_type or "").strip().lower()

    if equipment_type in {"escalator", "elevator"}:
        return "vibration_hz", 45.0, 55.0
    if equipment_type == "hvac":
        return "temperature_celsius", 18.0, 24.0
    if equipment_type == "food_court_exhaust":
        return "temperature_celsius", 35.0, 50.0
    if equipment_type == "generator":
        return "current_amps", 80.0, 120.0
    if equipment_type == "fire_alarm":
        return "current_amps", 0.5, 2.0
    if equipment_type == "restroom_sensor":
        return "occupancy_count", 0.0, 15.0
    if equipment_type == "parking_sensor":
        return "occupancy_count", 20.0, 80.0
    if equipment_type == "pressure_system":
        return "pressure_psi", 30.0, 50.0
    if equipment_type == "noise_monitor":
        return "noise_db", 40.0, 65.0

    return _facility_primary_metric(equipment_type), 40.0, 60.0


def run_facility_mission(app, property_id=None):
    from app.extensions import db

    with app.app_context():
        from app.models.agent import AgentAction, AgentConfiguration
        from app.models.facility import Equipment, WorkOrder
        from app.models.property import MallProperty
        from app.models.user import User
        from app.services import facility_service
        from app.services.notification_service import create_notification

        try:
            if property_id is not None:
                properties = MallProperty.query.filter_by(id=property_id, onboarding_complete=True).all()
            else:
                properties = MallProperty.query.filter_by(onboarding_complete=True).all()

            for property_record in properties:
                prop_id = property_record.id
                agent_config = AgentConfiguration.query.filter_by(property_id=prop_id).first()
                if agent_config is None or not agent_config.facility_mission_enabled:
                    continue

                equipment_list = Equipment.query.filter_by(property_id=prop_id, is_active=True).all()
                alerts_created = 0

                for equipment in equipment_list:
                    try:
                        fps_result = facility_service.compute_fps_for_equipment(equipment.id, prop_id)
                        if fps_result.get("insufficient_data"):
                            continue

                        fps_score = float(fps_result.get("fps_score") or 0.0)
                        if fps_score <= float(agent_config.facility_fps_threshold or 0.65):
                            continue

                        existing = AgentAction.query.filter_by(
                            entity_id=str(equipment.id),
                            mission_type="facility",
                            property_id=prop_id,
                            status="pending",
                        ).first()
                        if existing is not None:
                            continue

                        trend_text = "Slight upward trend"
                        if float(fps_result.get("normalized_slope") or 0.0) > 0.3:
                            trend_text = "Deteriorating (rising values)"
                        elif float(fps_result.get("normalized_slope") or 0.0) < 0.1:
                            trend_text = "Stable"

                        reasoning_prompt = (
                            "You are an AI predictive maintenance agent for a shopping mall. Provide a 2-3 sentence "
                            "maintenance recommendation based on these sensor anomaly findings:\n"
                            f"Equipment: {equipment.equipment_name} ({equipment.equipment_type})\n"
                            f"Location: Zone {equipment.zone}, Floor {equipment.floor}\n"
                            f"Manufacturer: {equipment.manufacturer or 'Unknown'}, Model: {equipment.model_number or 'Unknown'}\n"
                            f"Age: {float(fps_result.get('age_factor') or 0.0):.0%} of expected lifetime used\n"
                            f"Failure Probability Score: {fps_score:.2f}/1.00 (threshold: {agent_config.facility_fps_threshold})\n"
                            f"Anomaly Rate (24h): {float(fps_result.get('anomaly_rate') or 0.0):.0%} of readings are anomalous\n"
                            f"Trend Direction: {trend_text}\n"
                            f"Primary Sensor: {fps_result.get('primary_metric')} - Mean: {float(fps_result.get('mu') or 0.0):.2f}, "
                            f"Std Dev: {float(fps_result.get('sigma') or 0.0):.2f}\n"
                            "Recommend: specific maintenance action, urgency level, and estimated time frame."
                        )

                        fallback_reasoning = (
                            f"Equipment {equipment.equipment_name} in Zone {equipment.zone} shows FPS score of {fps_score:.2f}, "
                            f"indicating {float(fps_result.get('anomaly_rate') or 0.0):.0%} anomaly rate in the last 24 hours. "
                            f"Preventive maintenance is recommended. Contact the manufacturer ({equipment.manufacturer or 'vendor'}) "
                            f"and schedule inspection within {'24 hours' if fps_score > 0.85 else '3 days' if fps_score > 0.70 else '1 week'}."
                        )

                        gemini_reasoning_text = fallback_reasoning
                        if app.config.get("GEMINI_ENABLED", False):
                            try:
                                from google import genai

                                client = genai.Client()
                                response = client.models.generate_content(
                                    model="gemini-2.5-flash",
                                    contents=reasoning_prompt,
                                )
                                result_text = response.text
                                if result_text and result_text.strip():
                                    gemini_reasoning_text = result_text.strip()
                            except Exception:
                                app.logger.exception(
                                    "Gemini facility reasoning failed for equipment_id=%s property_id=%s",
                                    equipment.id,
                                    prop_id,
                                )

                        if fps_score > 0.85:
                            priority = "critical"
                        elif fps_score > 0.70:
                            priority = "high"
                        elif fps_score > 0.65:
                            priority = "medium"
                        else:
                            priority = "low"

                        estimated_cost = (
                            50000
                            if priority == "critical"
                            else 25000
                            if priority == "high"
                            else 10000
                            if priority == "medium"
                            else 5000
                        )

                        work_order = WorkOrder(
                            title=f"Preventive Maintenance: {equipment.equipment_name}",
                            description=gemini_reasoning_text,
                            priority=priority,
                            status="open",
                            property_id=prop_id,
                            equipment_id=equipment.id,
                            estimated_cost_inr=estimated_cost,
                            created_at=datetime.utcnow(),
                        )
                        db.session.add(work_order)
                        db.session.flush()

                        action = AgentAction(
                            mission_type="facility",
                            action_type="work_order_created",
                            description=(
                                f"Work order created for {equipment.equipment_name} - FPS: {fps_score:.2f}. "
                                f"{priority.title()} priority maintenance recommended."
                            ),
                            entity_id=str(equipment.id),
                            score=fps_score,
                            status="pending",
                            agent_reasoning=gemini_reasoning_text,
                            property_id=prop_id,
                            created_at=datetime.utcnow(),
                        )
                        db.session.add(action)
                        db.session.flush()

                        work_order.agent_action_id = action.id
                        db.session.commit()

                        if agent_config.auto_approve_maintenance:
                            action.status = "auto_executed"
                            action.resolved_at = datetime.utcnow()
                            db.session.commit()

                        recipients = User.query.filter(
                            User.property_id == prop_id,
                            User.role.in_(["mall_admin", "facility_manager"]),
                            User.is_active.is_(True),
                        ).all()

                        for user in recipients:
                            push_payload = None
                            if fps_score > 0.85:
                                push_payload = {
                                    "title": "Critical Equipment Alert",
                                    "body": (
                                        f"{equipment.equipment_name} in Zone {equipment.zone} "
                                        "immediate maintenance required"
                                    ),
                                    "icon": "/static/icons/icon-192.png",
                                    "badge": "/static/icons/icon-72.png",
                                    "tag": f"facility-alert-{equipment.id}",
                                    "data": {"url": f"/facility/{equipment.id}"},
                                    "actions": [
                                        {"action": "create", "title": "Create Work Order"},
                                        {"action": "view", "title": "View Details"},
                                    ],
                                    "vibrate": [200, 100, 200],
                                    "requireInteraction": True,
                                }
                            create_notification(
                                user_id=user.id,
                                title=f"\U0001F527 {'CRITICAL' if fps_score > 0.85 else 'Warning'}: {equipment.equipment_name}",
                                message=(
                                    f"FPS Score {fps_score:.2f} - Preventive maintenance recommended. "
                                    f"Work order #{work_order.id} created."
                                ),
                                notification_type="facility_alert",
                                severity="critical" if fps_score > 0.85 else "warning",
                                action_url=f"/facility/{equipment.id}",
                                property_id=prop_id,
                                push_payload=push_payload,
                            )

                            if agent_config.auto_approve_maintenance:
                                create_notification(
                                    user_id=user.id,
                                    title="Agent action auto executed",
                                    message=(
                                        f"Work order {work_order.id} was executed automatically."
                                    ),
                                    notification_type="agent_action",
                                    severity="info",
                                    action_url=f"/facility/{equipment.id}",
                                    property_id=prop_id,
                                    push_payload={
                                        "title": "Agent Action Completed",
                                        "body": (
                                            f"Maintenance auto executed for {equipment.equipment_name}"
                                        ),
                                        "icon": "/static/icons/icon-192.png",
                                        "badge": "/static/icons/icon-72.png",
                                        "tag": f"agent-action-{action.id}",
                                        "data": {"url": f"/facility/{equipment.id}"},
                                        "vibrate": [150, 100, 150],
                                        "requireInteraction": False,
                                    },
                                )

                        alerts_created += 1
                    except Exception:
                        db.session.rollback()
                        app.logger.exception(
                            "Facility mission failed for equipment_id=%s property_id=%s",
                            equipment.id,
                            prop_id,
                        )

                print(
                    f"[Facility Mission] Property {prop_id}: Checked {len(equipment_list)} equipment, "
                    f"{alerts_created} work orders created."
                )
        except Exception:
            db.session.rollback()
            app.logger.exception("Facility mission failed")


def simulate_sensor_readings(app):
    from app.extensions import db

    with app.app_context():
        from app.models.facility import Equipment, SensorReading
        from app.models.property import MallProperty

        try:
            equipment_list = (
                db.session.query(Equipment)
                .join(MallProperty, Equipment.property_id == MallProperty.id)
                .filter(
                    Equipment.is_active.is_(True),
                    MallProperty.onboarding_complete.is_(True),
                )
                .all()
            )

            if not equipment_list:
                return

            total_readings = 0
            property_ids = set()

            for equipment in equipment_list:
                property_ids.add(equipment.property_id)
                metric_name, normal_min, normal_max = _sensor_range(equipment)

                anomaly_probability = 0.10
                fps_score = float(equipment.fps_score or 0.0)
                if fps_score > 0.85:
                    anomaly_probability = 0.50
                elif fps_score > 0.70:
                    anomaly_probability = 0.30

                is_anomalous = random.random() < anomaly_probability

                mean_value = (normal_min + normal_max) / 2.0
                std_value = (normal_max - normal_min) / 6.0 if (normal_max - normal_min) > 0 else 1.0

                if not is_anomalous:
                    metric_value = random.uniform(normal_min, normal_max)
                    trend_shift = 0.0
                    if fps_score > 0.5:
                        trend_shift = fps_score * (normal_max - normal_min) * 0.1
                    metric_value = metric_value + trend_shift
                    z_score = (metric_value - mean_value) / std_value if std_value != 0 else 0.0
                else:
                    z_magnitude = random.uniform(3.0, 6.0) * random.choice([-1, 1])
                    metric_value = mean_value + z_magnitude * std_value
                    metric_value = max(0.0, metric_value)
                    z_score = z_magnitude

                reading = SensorReading(
                    equipment_id=equipment.id,
                    property_id=equipment.property_id,
                    metric_name=metric_name,
                    metric_value=round(metric_value, 3),
                    timestamp=datetime.utcnow(),
                    anomaly_flag=is_anomalous,
                    anomaly_score=round(abs(z_score), 4),
                    z_score=round(z_score, 4),
                )
                db.session.add(reading)
                total_readings += 1

            db.session.commit()

            cutoff = datetime.utcnow() - timedelta(days=3)
            SensorReading.query.filter(
                SensorReading.timestamp < cutoff,
                SensorReading.property_id.in_(list(property_ids)),
            ).delete(synchronize_session="fetch")
            db.session.commit()

            print(
                f"[Sensor Simulator] Generated {total_readings} readings for {len(equipment_list)} equipment units."
            )
        except Exception:
            db.session.rollback()
            app.logger.exception("Sensor reading simulation failed")


def run_facility_fps_job(app):
    try:
        run_facility_mission(app)
    except Exception as e:
        print(f"[Facility FPS Job Error] {e}")


def send_daily_briefing(app):
    from app.extensions import db

    with app.app_context():
        from app.models.agent import AgentAction
        from app.models.campaign import Campaign
        from app.models.facility import WorkOrder
        from app.models.user import User
        from app.services.email_service import send_morning_briefing_email
        from app.services.notification_service import create_notification

        try:
            users = User.query.filter_by(role="mall_admin", is_active=True, is_verified=True).all()
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            sent_count = 0
            for user in users:
                if not user.property_id:
                    continue

                inventory_alerts = AgentAction.query.filter(
                    AgentAction.property_id == user.property_id,
                    AgentAction.mission_type == "inventory",
                    AgentAction.created_at >= today_start,
                ).count()

                campaign_opportunities = Campaign.query.filter(
                    Campaign.property_id == user.property_id,
                    Campaign.status == "opportunity",
                    Campaign.created_at >= today_start,
                ).count()

                open_work_orders = WorkOrder.query.filter(
                    WorkOrder.property_id == user.property_id,
                    WorkOrder.status == "open",
                ).count()

                agent_actions_overnight = AgentAction.query.filter(
                    AgentAction.property_id == user.property_id,
                    AgentAction.created_at >= today_start,
                ).count()

                create_notification(
                    user_id=user.id,
                    title="\u2600\ufe0f Good Morning - Today's RetailMind Briefing",
                    message=(
                        f"{inventory_alerts} inventory alerts | {campaign_opportunities} campaign opportunities | "
                        f"{open_work_orders} open work orders | {agent_actions_overnight} overnight agent actions"
                    ),
                    notification_type="system",
                    severity="info",
                    action_url="/dashboard",
                    property_id=user.property_id,
                    push_payload={
                        "title": f"Good Morning, {user.full_name.split(' ')[0] if user.full_name else 'there'}",
                        "body": (
                            f"{inventory_alerts} inventory alerts, {campaign_opportunities} campaign opportunities, "
                            f"{open_work_orders} open work orders"
                        ),
                        "icon": "/static/icons/icon-192.png",
                        "badge": "/static/icons/icon-72.png",
                        "tag": f"daily-briefing-{user.id}",
                        "data": {"url": "/dashboard"},
                        "vibrate": [120, 80, 120],
                        "requireInteraction": False,
                    },
                )

                brief_data = {
                    "inventory_alerts": inventory_alerts,
                    "campaign_opportunities": campaign_opportunities,
                    "open_work_orders": open_work_orders,
                    "overnight_agent_actions": agent_actions_overnight,
                }

                # For MVP this runs at 8:00 UTC. In production, adjust cron to 2:30 UTC for 8:00 IST.
                if app.config.get("MAIL_USERNAME"):
                    send_morning_briefing_email(user, brief_data)

                sent_count += 1

            db.session.commit()
            print(f"[Daily Briefing] Sent briefings to {sent_count} mall admins.")
        except Exception:
            db.session.rollback()
            app.logger.exception("Daily briefing job failed")


def cleanup_expired_tokens(app):
    from app.extensions import db

    with app.app_context():
        from app.models.user import EmailVerificationToken, PasswordResetToken

        try:
            EmailVerificationToken.query.filter(
                db.or_(
                    EmailVerificationToken.expires_at < datetime.utcnow(),
                    EmailVerificationToken.used.is_(True),
                )
            ).delete(synchronize_session=False)

            PasswordResetToken.query.filter(
                db.or_(
                    PasswordResetToken.expires_at < datetime.utcnow(),
                    PasswordResetToken.used.is_(True),
                )
            ).delete(synchronize_session=False)

            db.session.commit()
            print("[Token Cleanup] Removed expired tokens.")
        except Exception:
            db.session.rollback()
            app.logger.exception("Expired token cleanup failed")
