import json
from datetime import date, datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models.campaign import Campaign
from app.models.inventory import FootTraffic
from app.models.property import MallProperty
from app.models.tenant import Tenant


def _clamp(value, low=0.0, high=1.0):
    return min(high, max(low, value))


def _clean_json_text(raw_text):
    if raw_text is None:
        return ""

    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    return clean


def _seasonal_weather_factor(category, month):
    category_norm = (category or "").strip().lower()

    if month in [10, 11, 12, 1, 2]:
        if category_norm in {"fashion", "sportswear", "footwear"}:
            return 0.80
        return 0.75

    if month in [3, 4, 5]:
        if category_norm in {"fashion", "jewellery"}:
            return 0.70
        if category_norm in {"food & beverage", "food", "f&b"}:
            return 0.85
        return 0.75

    if month in [6, 7, 8, 9]:
        if category_norm in {"fashion", "sportswear", "footwear"}:
            return 0.60
        if category_norm in {"food & beverage", "food", "f&b"}:
            return 0.85
        return 0.65

    return 0.65


def _weather_match_factor(category, condition, temperature):
    category_norm = (category or "").strip().lower()
    condition_norm = (condition or "").strip().lower()

    is_sunny = condition_norm in {"sunny", "clear", "hot"}
    is_cool = condition_norm in {"cool", "pleasant"}
    is_cloudy = condition_norm == "cloudy"
    is_rainy = condition_norm in {"rainy", "foggy", "monsoon"}

    if category_norm in {"sportswear", "footwear"}:
        if is_sunny:
            return 0.90
        if is_cool:
            return 0.85
        if is_cloudy:
            return 0.70
        if is_rainy:
            return 0.40
        if temperature is not None and temperature >= 34:
            return 0.88
        return 0.70

    if category_norm in {"food & beverage", "food", "f&b"}:
        if is_rainy:
            return 0.90
        if condition_norm == "hot" or (temperature is not None and temperature >= 34):
            return 0.85
        return 0.75

    if category_norm in {"fashion", "jewellery"}:
        if is_cool:
            return 0.85
        if is_sunny:
            return 0.80
        if is_rainy:
            return 0.55
        return 0.70

    if category_norm == "electronics":
        return 0.70

    return 0.65


def _festival_dates_for_year(year):
    diwali = date(year, 11, 1)
    return {
        "Diwali": diwali,
        "Dhanteras": diwali - timedelta(days=1),
        "Holi": date(year, 3, 14),
        "Eid": date(year, 3, 31),
        "Christmas": date(year, 12, 25),
        "New Year": date(year, 1, 1),
        "Republic Day Sale": date(year, 1, 26),
        "Independence Day Sale": date(year, 8, 15),
        "Dussehra": date(year, 10, 20),
        "Navratri": date(year, 10, 14),
        "Valentine's Day": date(year, 2, 14),
        "Women's Day": date(year, 3, 8),
    }


def _event_proximity_factor(today):
    best_score = 0.0
    best_label = ""
    smallest_gap = 9999

    for target_year in [today.year - 1, today.year, today.year + 1]:
        festivals = _festival_dates_for_year(target_year)
        for event_name, event_date in festivals.items():
            distance = abs((event_date - today).days)

            if distance <= 7:
                score = 1.0
            elif distance <= 14:
                score = 0.7
            elif distance <= 30:
                score = 0.4
            else:
                score = 0.0

            if score > best_score or (score == best_score and score > 0 and distance < smallest_gap):
                best_score = score
                best_label = event_name
                smallest_gap = distance

    return _clamp(best_score), best_label


def compute_cos_for_tenant_zone(tenant_id, zone_id, property_id):
    try:
        now = datetime.utcnow()

        tenant = Tenant.query.filter_by(id=tenant_id, property_id=property_id).first()
        mall_property = MallProperty.query.get(property_id)

        if tenant is None or mall_property is None:
            return {
                "tenant_id": tenant_id,
                "zone_id": zone_id,
                "cos_score": 0.0,
                "error": "Tenant or property not found",
            }

        seven_days_ago = now - timedelta(days=7)

        latest_traffic = (
            FootTraffic.query.filter(
                FootTraffic.property_id == property_id,
                FootTraffic.zone_id == zone_id,
            )
            .order_by(FootTraffic.timestamp.desc())
            .first()
        )

        if latest_traffic is None:
            TF = 0.5
        else:
            max_count = (
                db.session.query(db.func.max(FootTraffic.count))
                .filter(
                    FootTraffic.property_id == property_id,
                    FootTraffic.zone_id == zone_id,
                    FootTraffic.timestamp >= seven_days_ago,
                )
                .scalar()
            )
            if max_count and max_count > 0:
                TF = float(latest_traffic.count or 0) / float(max_count)
            else:
                TF = 0.5

        TF = _clamp(TF)

        promotional_campaign_exists = (
            Campaign.query.filter(
                Campaign.tenant_id == tenant.id,
                Campaign.property_id == property_id,
                Campaign.status.in_(["opportunity", "active", "pending_activation"]),
                Campaign.created_at >= seven_days_ago,
                Campaign.campaign_copy.isnot(None),
                Campaign.campaign_copy != "",
            )
            .limit(1)
            .first()
            is not None
        )
        TP = 1.0 if promotional_campaign_exists else 0.5
        TP = _clamp(TP)

        weather_context_str = "Seasonal baseline"
        WM = _seasonal_weather_factor(tenant.category, now.month)
        city_name = mall_property.city or "Mumbai"

        if current_app.config.get("GEMINI_ENABLED", False):
            try:
                from google import genai
                from google.genai import types

                client = genai.Client()
                grounding_tool = types.Tool(google_search=types.GoogleSearch())
                config = types.GenerateContentConfig(tools=[grounding_tool])
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=(
                        f"What is the current weather in {city_name}, India right now? "
                        "Respond with ONLY a JSON object in this exact format: "
                        '{"condition": "sunny|cloudy|rainy|foggy|hot|cool", "temperature_celsius": 28, '
                        '"description": "Clear skies, warm afternoon"}'
                    ),
                    config=config,
                )
                result_text = response.text

                weather_payload = json.loads(_clean_json_text(result_text))
                weather_condition = str(weather_payload.get("condition", "")).strip().lower()
                weather_temp = weather_payload.get("temperature_celsius")
                weather_description = str(weather_payload.get("description", "")).strip()

                try:
                    weather_temp = float(weather_temp) if weather_temp is not None else None
                except (TypeError, ValueError):
                    weather_temp = None

                WM = _weather_match_factor(tenant.category, weather_condition, weather_temp)
                WM = _clamp(WM)

                if weather_description:
                    weather_context_str = weather_description
                else:
                    weather_context_str = f"{weather_condition.title()} conditions"
            except Exception:
                current_app.logger.exception(
                    "Gemini weather lookup failed for tenant_id=%s property_id=%s",
                    tenant_id,
                    property_id,
                )
                WM = _seasonal_weather_factor(tenant.category, now.month)
                weather_context_str = "Seasonal baseline used because weather lookup failed"
        else:
            WM = _seasonal_weather_factor(tenant.category, now.month)
            weather_context_str = "Seasonal baseline used because Gemini is disabled"

        WM = _clamp(WM)

        EM, event_name = _event_proximity_factor(now.date())
        event_context_str = event_name if event_name else ""

        LP = 0.5

        recent_active_campaign = (
            Campaign.query.filter(
                Campaign.tenant_id == tenant.id,
                Campaign.property_id == property_id,
                Campaign.status == "active",
                Campaign.activated_at >= now - timedelta(hours=2),
            )
            .limit(1)
            .first()
            is not None
        )
        RC = 1.0 if recent_active_campaign else 0.0

        COS_raw = 0.30 * TF + 0.20 * TP + 0.20 * WM + 0.15 * EM + 0.15 * LP
        COS = COS_raw * (1.0 - RC)
        COS = _clamp(COS)

        return {
            "tenant_id": tenant_id,
            "zone_id": zone_id,
            "cos_score": round(COS, 4),
            "tf": round(TF, 4),
            "tp": round(TP, 4),
            "wm": round(WM, 4),
            "em": round(EM, 4),
            "lp": round(LP, 4),
            "rc": round(RC, 4),
            "weather_context": weather_context_str,
            "event_context": event_context_str,
        }
    except Exception as e:
        current_app.logger.exception(
            "Failed to compute COS for tenant_id=%s zone_id=%s property_id=%s",
            tenant_id,
            zone_id,
            property_id,
        )
        return {"tenant_id": tenant_id, "zone_id": zone_id, "cos_score": 0.0, "error": str(e)}


def generate_campaign_copy(tenant, zone_id, cos_result, property_city):
    fallback = {
        "campaign_name": f"Flash Sale at {tenant.name} - Zone {zone_id}",
        "campaign_copy": f"Visit {tenant.name} in Zone {zone_id} for exclusive deals today!",
        "target_audience_description": f"Mall visitors browsing {tenant.category} products",
        "recommended_channel": "in_app",
    }

    if not current_app.config.get("GEMINI_ENABLED", False):
        return fallback

    try:
        from google import genai

        prompt = (
            "You are a retail marketing expert specializing in Indian shopping malls. Generate a compelling campaign for the following scenario:\n\n"
            f"Store: {tenant.name}\n"
            f"Category: {tenant.category}\n"
            f"Location: Zone {zone_id}, {property_city} Mall\n"
            f"Weather Context: {cos_result.get('weather_context', '')}\n"
            f"Event Context: {cos_result.get('event_context', '')}\n"
            f"Foot Traffic Level: {'High' if cos_result.get('tf', 0) > 0.7 else 'Medium' if cos_result.get('tf', 0) > 0.4 else 'Low'}\n"
            f"Campaign Opportunity Score: {cos_result.get('cos_score', 0):.2f}/1.00\n\n"
            "Generate a campaign in Indian retail context. Respond ONLY with a JSON object in this exact format with no extra text:\n"
            "{\n"
            '  "campaign_name": "Short catchy campaign name (max 60 chars)",\n'
            '  "campaign_copy": "2-3 sentence promotional copy mentioning the store, offer, and location. Use Indian retail sensibility. Include a call to action.",\n'
            '  "target_audience_description": "1 sentence describing the target audience for this campaign",\n'
            '  "recommended_channel": "push_notification or in_app or digital_signage or sms or email"\n'
            "}"
        )

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        result_text = response.text

        parsed = json.loads(_clean_json_text(result_text))
        campaign_name = str(parsed.get("campaign_name") or "").strip() or fallback["campaign_name"]
        campaign_copy = str(parsed.get("campaign_copy") or "").strip() or fallback["campaign_copy"]
        audience = (
            str(parsed.get("target_audience_description") or "").strip()
            or fallback["target_audience_description"]
        )
        channel = str(parsed.get("recommended_channel") or "").strip().lower() or fallback["recommended_channel"]

        if channel not in {"push_notification", "in_app", "digital_signage", "sms", "email"}:
            channel = "in_app"

        return {
            "campaign_name": campaign_name[:200],
            "campaign_copy": campaign_copy[:2000],
            "target_audience_description": audience[:500],
            "recommended_channel": channel,
        }
    except Exception:
        current_app.logger.exception("Gemini campaign copy generation failed for tenant_id=%s", tenant.id)
        return fallback


def get_active_campaigns(property_id):
    return (
        db.session.query(Campaign, Tenant)
        .outerjoin(Tenant, Campaign.tenant_id == Tenant.id)
        .filter(Campaign.property_id == property_id, Campaign.status == "active")
        .order_by(Campaign.activated_at.desc())
        .all()
    )


def get_campaign_opportunities(property_id, limit=10):
    return (
        db.session.query(Campaign, Tenant)
        .outerjoin(Tenant, Campaign.tenant_id == Tenant.id)
        .filter(
            Campaign.property_id == property_id,
            Campaign.status.in_(["opportunity", "pending_activation"]),
        )
        .order_by(Campaign.opportunity_score.desc())
        .limit(limit)
        .all()
    )


def get_campaign_history(property_id, page=1, per_page=20):
    return (
        Campaign.query.filter(
            Campaign.property_id == property_id,
            Campaign.status.in_(["completed", "paused", "rejected"]),
        )
        .order_by(Campaign.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def _hour_weight(hour):
    if 17 <= hour <= 22:
        return 1.8
    if 12 <= hour <= 16:
        return 1.2
    if 9 <= hour <= 11:
        return 1.0
    if 0 <= hour <= 8:
        return 0.4
    return 0.6


def _distribute_total(total_value, weights):
    if not weights:
        return []

    total_value = int(total_value or 0)
    if total_value <= 0:
        return [0 for _ in weights]

    weight_sum = sum(weights)
    if weight_sum <= 0:
        base = total_value // len(weights)
        values = [base for _ in weights]
        for idx in range(total_value - base * len(weights)):
            values[idx % len(values)] += 1
        return values

    raw_values = [(total_value * weight / weight_sum) for weight in weights]
    values = [int(value) for value in raw_values]

    remaining = total_value - sum(values)
    if remaining > 0:
        priority = sorted(range(len(weights)), key=lambda idx: raw_values[idx] - values[idx], reverse=True)
        for idx in range(remaining):
            values[priority[idx % len(priority)]] += 1

    return values


def get_campaign_hourly_performance(campaign_id):
    campaign = Campaign.query.get(campaign_id)
    if campaign is None or campaign.activated_at is None:
        return {
            "hours": [],
            "metrics": {
                "impressions_per_hour": [],
                "clicks_per_hour": [],
            },
        }

    start = campaign.activated_at.replace(minute=0, second=0, microsecond=0)
    max_end = start + timedelta(hours=72)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    end = min(now, max_end)

    if end < start:
        end = start

    hours = []
    cursor = start
    while cursor <= end:
        hours.append(cursor)
        cursor += timedelta(hours=1)

    weights = [_hour_weight(hour_item.hour) for hour_item in hours]
    impressions = _distribute_total(campaign.impressions or 0, weights)
    clicks = _distribute_total(campaign.clicks or 0, weights)

    for idx in range(len(clicks)):
        clicks[idx] = min(clicks[idx], impressions[idx])

    return {
        "hours": [hour_item.strftime("%d %b %I%p").replace(" 0", " ") for hour_item in hours],
        "metrics": {
            "impressions_per_hour": impressions,
            "clicks_per_hour": clicks,
        },
    }
