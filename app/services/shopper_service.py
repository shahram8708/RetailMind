import json
import time
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.campaign import Campaign
from app.models.inventory import InventoryItem
from app.models.property import MallProperty
from app.models.shopper import ShopperInteraction
from app.models.tenant import Tenant


def _fallback_intent(query_text):
    return {
        "product_category": None,
        "brand": None,
        "color": None,
        "size": None,
        "max_price_inr": None,
        "min_price_inr": None,
        "keywords": query_text.split()[:5],
        "gender": None,
    }


def _clean_json_response_text(raw_text):
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text[3:]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _to_float_or_none(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_intent(intent_dict, query_text):
    fallback = _fallback_intent(query_text)
    if not isinstance(intent_dict, dict):
        return fallback

    normalized = {
        "product_category": intent_dict.get("product_category") or None,
        "brand": intent_dict.get("brand") or None,
        "color": intent_dict.get("color") or None,
        "size": intent_dict.get("size") or None,
        "max_price_inr": _to_float_or_none(intent_dict.get("max_price_inr")),
        "min_price_inr": _to_float_or_none(intent_dict.get("min_price_inr")),
        "keywords": intent_dict.get("keywords") if isinstance(intent_dict.get("keywords"), list) else [],
        "gender": intent_dict.get("gender") or None,
    }

    clean_keywords = []
    for keyword in normalized["keywords"]:
        if keyword is None:
            continue
        kw = str(keyword).strip()
        if kw:
            clean_keywords.append(kw)
    if not clean_keywords:
        clean_keywords = query_text.split()[:5]

    normalized["keywords"] = clean_keywords[:10]
    return normalized


def _extract_intent_with_gemini(query_text):
    prompt = (
        "You are a shopping assistant AI for an Indian mall. Extract the product search intent from this shopper query and respond ONLY with a valid JSON object no markdown no explanation no extra text.\n\n"
        f"Query: \"{query_text}\"\n\n"
        "Respond with exactly this JSON format:\n"
        "{\n"
        "  \"product_category\": \"one of: Fashion, Sportswear, Electronics, Footwear, Jewellery, Food & Beverage, Pharmacy, Books, Toys & Games, Home & Decor, Beauty & Personal Care, Entertainment, Services, or null if unclear\",\n"
        "  \"brand\": \"brand name as string or null\",\n"
        "  \"color\": \"color as string or null\",\n"
        "  \"size\": \"size as string (e.g. M, L, UK8, 8, XL, 32) or null\",\n"
        "  \"max_price_inr\": \"maximum price as number or null\",\n"
        "  \"min_price_inr\": \"minimum price as number or null\",\n"
        "  \"keywords\": [\"list\", \"of\", \"key\", \"search\", \"terms\"],\n"
        "  \"gender\": \"Men, Women, Unisex, Kids, or null\"\n"
        "}"
    )

    try:
        from google import genai

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        cleaned = _clean_json_response_text(response.text)
        parsed = json.loads(cleaned)
        return _normalize_intent(parsed, query_text)
    except json.JSONDecodeError:
        current_app.logger.exception("Gemini intent JSON parsing failed for shopper query")
        return _fallback_intent(query_text)
    except Exception:
        current_app.logger.exception("Gemini intent extraction failed for shopper query")
        return _fallback_intent(query_text)


def _build_base_query(property_id):
    return (
        db.session.query(InventoryItem, Tenant)
        .join(Tenant, InventoryItem.tenant_id == Tenant.id)
        .filter(
            InventoryItem.property_id == property_id,
            Tenant.property_id == property_id,
            InventoryItem.stock_level > 0,
        )
    )


def _apply_intent_filters(base_query, intent_dict):
    query = base_query

    if intent_dict.get("product_category") is not None:
        category_term = f"%{intent_dict['product_category']}%"
        query = query.filter(
            db.or_(
                InventoryItem.category.ilike(category_term),
                Tenant.category.ilike(category_term),
            )
        )

    if intent_dict.get("brand") is not None:
        query = query.filter(InventoryItem.brand.ilike(f"%{intent_dict['brand']}%"))

    if intent_dict.get("color") is not None:
        query = query.filter(InventoryItem.color.ilike(f"%{intent_dict['color']}%"))

    if intent_dict.get("size") is not None:
        query = query.filter(InventoryItem.size.ilike(f"%{intent_dict['size']}%"))

    if intent_dict.get("max_price_inr") is not None:
        query = query.filter(InventoryItem.unit_price <= float(intent_dict["max_price_inr"]))

    if intent_dict.get("min_price_inr") is not None:
        query = query.filter(InventoryItem.unit_price >= float(intent_dict["min_price_inr"]))

    keywords = intent_dict.get("keywords") or []
    keyword_filters = [InventoryItem.product_name.ilike(f"%{keyword}%") for keyword in keywords if keyword]
    if keyword_filters:
        query = query.filter(db.or_(*keyword_filters))

    return query


def _score_and_rank_results(results, intent_dict):
    scored_results = []
    active_campaign_cache = {}

    for item, tenant in results:
        score = 0.0

        if intent_dict.get("brand") and item.brand:
            if item.brand.lower() == str(intent_dict["brand"]).lower():
                score += 0.40
            elif str(intent_dict["brand"]).lower() in item.brand.lower():
                score += 0.25

        if intent_dict.get("size") and item.size:
            if item.size.lower() == str(intent_dict["size"]).lower():
                score += 0.25

        if intent_dict.get("color") and item.color:
            if item.color.lower() == str(intent_dict["color"]).lower():
                score += 0.15

        if intent_dict.get("max_price_inr") and item.unit_price:
            max_price = float(intent_dict["max_price_inr"])
            if max_price > 0:
                price_ratio = float(item.unit_price) / max_price
                if price_ratio <= 1.0:
                    score += 0.10 * (1 - price_ratio)

        if tenant.id not in active_campaign_cache:
            active_campaign_cache[tenant.id] = Campaign.query.filter_by(
                tenant_id=tenant.id,
                status="active",
            ).first()

        active_campaign = active_campaign_cache.get(tenant.id)
        if active_campaign:
            score += 0.10

        stock_ratio = min(1.0, float(item.stock_level or 0) / float(max(item.reorder_threshold or 0, 1)))
        score += 0.05 * stock_ratio

        item._relevance_score = round(score, 4)
        item._active_campaign = active_campaign
        scored_results.append((item, tenant))

    scored_results.sort(key=lambda row: row[0]._relevance_score, reverse=True)
    return scored_results[:5]


def get_results_from_intent(intent_dict, property_id):
    intent = _normalize_intent(intent_dict or {}, "")
    base_query = _build_base_query(property_id)
    strict_query = _apply_intent_filters(base_query, intent)
    results = strict_query.limit(50).all()

    if not results:
        relaxed_query = _build_base_query(property_id)
        keywords = intent.get("keywords") or []
        broad_keywords = keywords[:2]
        broad_filters = [InventoryItem.product_name.ilike(f"%{keyword}%") for keyword in broad_keywords if keyword]
        if broad_filters:
            relaxed_query = relaxed_query.filter(db.or_(*broad_filters))
        results = relaxed_query.limit(50).all()

    return _score_and_rank_results(results, intent)


def _navigation_fallback(tenant):
    floor_step = (
        "Take the escalator to Floor " + str(tenant.floor)
        if int(tenant.floor or 0) > 0
        else "Stay on the Ground Floor"
    )
    side = "left" if (tenant.zone or "").upper() in ["A", "B"] else "right"
    return (
        "1. Enter from the Main Entrance Ground Floor Center\n"
        f"2. {floor_step}\n"
        f"3. Head towards Zone {tenant.zone}\n"
        f"4. Look for Unit {tenant.unit_number} {tenant.name} is on your {side}"
    )


def _generate_navigation_for_tenant(tenant):
    prompt = (
        "Generate step by step walking directions for a mall visitor to find this store. Keep it natural concise and easy to follow 3 to 4 steps maximum:\n\n"
        f"Store: {tenant.name}\n"
        f"Zone: Zone {tenant.zone}\n"
        f"Floor: {'Ground Floor' if int(tenant.floor or 0) == 0 else f'Floor {tenant.floor}'}\n"
        f"Unit Number: {tenant.unit_number}\n"
        "Mall Layout: The mall has zones A through E. Zone A is the left wing fashion and jewellery, Zone B is the center left sports and active, Zone C is center right electronics and services, Zone D is the food court ground floor, Zone E is the right wing general stores.\n\n"
        "Start from the main entrance ground floor center. Provide directions.\n\n"
        "Format as numbered steps: 1. ... 2. ... 3. ..."
    )

    try:
        from google import genai

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = (response.text or "").strip()
        if not text:
            return _navigation_fallback(tenant)
        return text
    except Exception:
        current_app.logger.exception("Gemini navigation generation failed for tenant_id=%s", tenant.id)
        return _navigation_fallback(tenant)


def generate_navigation_instructions(tenant):
    return _generate_navigation_for_tenant(tenant)


def process_query(query_text, property_id, session_id=None, shopper_user_id=None):
    try:
        start_time = time.time()

        if current_app.config.get("GEMINI_ENABLED", False):
            intent_dict = _extract_intent_with_gemini(query_text)
        else:
            intent_dict = _fallback_intent(query_text)

        top_results = get_results_from_intent(intent_dict, property_id)

        nav_instructions = {}
        for item, tenant in top_results:
            nav_instructions[item.sku_id] = _generate_navigation_for_tenant(tenant)

        response_time_ms = int((time.time() - start_time) * 1000)

        interaction = ShopperInteraction(
            property_id=property_id,
            session_id=session_id,
            shopper_user_id=shopper_user_id,
            query_text=query_text,
            results_returned=len(top_results),
            purchase_completed=False,
            timestamp=datetime.utcnow(),
            gemini_intent_extracted=json.dumps(intent_dict),
            response_time_ms=response_time_ms,
        )
        db.session.add(interaction)
        db.session.commit()

        return {
            "query_id": interaction.id,
            "query_text": query_text,
            "intent": intent_dict,
            "results": [
                {
                    "sku_id": item.sku_id,
                    "product_name": item.product_name,
                    "brand": item.brand,
                    "category": item.category,
                    "color": item.color,
                    "size": item.size,
                    "unit_price": item.unit_price,
                    "stock_level": item.stock_level,
                    "stock_status": (
                        "In Stock"
                        if (item.stock_level or 0) > (item.reorder_threshold or 0)
                        else "Low Stock"
                        if (item.stock_level or 0) > 0
                        else "Out of Stock"
                    ),
                    "tenant_name": tenant.name,
                    "tenant_zone": tenant.zone,
                    "tenant_floor": tenant.floor,
                    "tenant_unit": tenant.unit_number,
                    "floor_label": "Ground Floor" if int(tenant.floor or 0) == 0 else f"Floor {tenant.floor}",
                    "active_campaign": item._active_campaign.campaign_name if item._active_campaign else None,
                    "discount_text": item._active_campaign.campaign_copy[:80] if item._active_campaign and item._active_campaign.campaign_copy else None,
                    "nav_instructions": nav_instructions.get(item.sku_id, ""),
                    "relevance_score": item._relevance_score,
                }
                for item, tenant in top_results
            ],
            "results_count": len(top_results),
            "response_time_ms": response_time_ms,
            "property_id": property_id,
        }
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Shopper process_query failed")
        return {
            "query_id": None,
            "results": [],
            "results_count": 0,
            "error": str(exc),
        }


def log_result_click(query_id, sku_id):
    try:
        interaction = ShopperInteraction.query.get(query_id)
        if not interaction:
            return False
        interaction.result_clicked = sku_id
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to log shopper result click")
        return False


def get_active_promotions(property_id, limit=8):
    rows = (
        db.session.query(Campaign, Tenant)
        .join(Tenant, Campaign.tenant_id == Tenant.id)
        .filter(
            Campaign.property_id == property_id,
            Campaign.status == "active",
            Tenant.property_id == property_id,
        )
        .order_by(Campaign.activated_at.desc())
        .limit(limit)
        .all()
    )
    return rows


def get_property_for_shopper(property_id):
    return MallProperty.query.get(property_id)
