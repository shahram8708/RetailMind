import json
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.models.property import MallProperty
from app.models.shopper import ShopperInteraction
from app.services import shopper_service


shopper_bp = Blueprint("shopper", __name__)


def _fallback_navigation(tenant):
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


@shopper_bp.route("", methods=["GET"])
@shopper_bp.route("/", methods=["GET"])
def index():
    property_id = request.args.get("property_id", type=int)

    if not property_id:
        default_property = MallProperty.query.filter_by(onboarding_complete=True).first()
        if not default_property:
            flash("No mall configured yet.", "warning")
            return redirect(url_for("public.index"))
        property_id = default_property.id

    property_record = shopper_service.get_property_for_shopper(property_id)
    if not property_record:
        flash("Mall not found.", "warning")
        return redirect(url_for("public.index"))

    promotions = shopper_service.get_active_promotions(property_id, limit=8)
    recent_searches = session.get("shopper_recent_searches", [])

    return render_template(
        "shopper/index.html",
        property=property_record,
        promotions=promotions,
        recent_searches=recent_searches,
        property_id=property_id,
    )


@shopper_bp.route("/result/<int:query_id>", methods=["GET"])
def results(query_id):
    interaction = ShopperInteraction.query.get_or_404(query_id)

    if interaction.timestamp and (datetime.utcnow() - interaction.timestamp) > timedelta(minutes=30):
        flash("Session expired. Please search again.", "warning")
        return redirect(url_for("shopper.index", property_id=interaction.property_id))

    property_record = MallProperty.query.get(interaction.property_id)

    intent_dict = {}
    if interaction.gemini_intent_extracted:
        try:
            intent_dict = json.loads(interaction.gemini_intent_extracted)
        except Exception:
            intent_dict = {}

    ranked_rows = shopper_service.get_results_from_intent(intent_dict, interaction.property_id)

    results_payload = []
    for index_value, (item, tenant) in enumerate(ranked_rows, start=1):
        if index_value == 1:
            nav_text = shopper_service.generate_navigation_instructions(tenant)
        else:
            nav_text = _fallback_navigation(tenant)

        active_campaign = getattr(item, "_active_campaign", None)

        results_payload.append(
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
                "active_campaign": active_campaign.campaign_name if active_campaign else None,
                "discount_text": active_campaign.campaign_copy[:80] if active_campaign and active_campaign.campaign_copy else None,
                "nav_instructions": nav_text,
                "relevance_score": getattr(item, "_relevance_score", 0.0),
            }
        )

    return render_template(
        "shopper/results.html",
        interaction=interaction,
        property=property_record,
        intent=intent_dict,
        results=results_payload,
        results_count=len(results_payload),
    )


@shopper_bp.route("/log-click", methods=["POST"])
def log_click():
    payload = request.get_json(silent=True) or {}
    query_id = payload.get("query_id")
    sku_id = payload.get("sku_id")

    if query_id is None or not sku_id:
        return jsonify({"success": False, "error": "Missing query_id or sku_id"}), 400

    success = shopper_service.log_result_click(query_id, sku_id)
    if not success:
        return jsonify({"success": False}), 404

    return jsonify({"success": True}), 200


@shopper_bp.route("/clear-recent", methods=["POST"])
def clear_recent_searches():
    session["shopper_recent_searches"] = []
    session.modified = True
    return jsonify({"success": True}), 200
