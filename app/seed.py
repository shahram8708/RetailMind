import random
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models.agent import AgentAction, AgentConfiguration
from app.models.billing import Subscription
from app.models.campaign import Campaign
from app.models.facility import Equipment, SensorReading
from app.models.inventory import FootTraffic, InventoryItem, SalesVelocity
from app.models.notification import Notification
from app.models.property import MallProperty
from app.models.tenant import Tenant
from app.models.user import User


def _supplier_defaults(brand):
    normalized = (
        brand.lower()
        .replace("'", "")
        .replace(" ", "")
        .replace("&", "and")
        .replace(".", "")
    )
    return f"{brand} India Distribution", f"supply@{normalized}.com"


def seed_database_if_empty():
    if User.query.first() is not None:
        return

    rng = random.Random(42)
    now = datetime.utcnow()

    try:
        users_data = [
            ("Arjun Kapoor", "superadmin@retailmind.ai", "SuperAdmin@123", "superadmin", True, True),
            ("Rajan Mehta", "rajan@phoenixmall.com", "MallAdmin@123", "mall_admin", True, True),
            ("Anika Reddy", "anika@phoenixmall.com", "Marketing@123", "marketing_manager", True, True),
            ("Suresh Pillai", "sureshp@phoenixmall.com", "Facility@123", "facility_manager", True, True),
            ("Priya Sharma", "priya@zara.com", "StoreManager@123", "store_manager", True, True),
            ("Vikram Iyer", "vikram@nike.com", "StoreManager@123", "store_manager", True, True),
            ("Anand Pillai", "anand@apple.com", "StoreManager@123", "store_manager", True, True),
            ("Meena Reddy", "meena@tanishq.com", "StoreManager@123", "store_manager", True, True),
            ("Suresh Kumar", "suresh@mcdonalds.com", "StoreManager@123", "store_manager", True, True),
        ]

        users = {}
        for full_name, email, password, role, verified, active in users_data:
            user = User(
                full_name=full_name,
                email=email,
                role=role,
                is_verified=verified,
                is_active=active,
            )
            user.set_password(password)
            db.session.add(user)
            users[email] = user

        db.session.flush()

        mall_admin = users["rajan@phoenixmall.com"]

        mall_property = MallProperty(
            name="Phoenix Marketcity Mumbai",
            location="LBS Marg, Kurla West, Mumbai 400070, Maharashtra",
            city="Mumbai",
            country="India",
            total_area_sqft=1200000,
            num_floors=4,
            num_tenants=220,
            owner_user_id=mall_admin.id,
            elasticsearch_index_prefix="phoenix_mumbai",
            subscription_tier="professional",
            onboarding_complete=True,
        )
        db.session.add(mall_property)
        db.session.flush()

        for user in users.values():
            if user.role != "superadmin":
                user.property_id = mall_property.id

        tenant_specs = [
            {
                "key": "zara",
                "name": "Zara Fashion",
                "category": "Fashion",
                "zone": "A",
                "floor": 1,
                "unit_number": "A-101",
                "manager": users["priya@zara.com"],
                "contact_email": "priya@zara.com",
                "contact_phone": "+91 98765 12001",
            },
            {
                "key": "nike",
                "name": "Nike Store",
                "category": "Sportswear",
                "zone": "B",
                "floor": 2,
                "unit_number": "B-201",
                "manager": users["vikram@nike.com"],
                "contact_email": "vikram@nike.com",
                "contact_phone": "+91 98765 12002",
            },
            {
                "key": "apple",
                "name": "Apple Authorised Reseller",
                "category": "Electronics",
                "zone": "C",
                "floor": 1,
                "unit_number": "C-102",
                "manager": users["anand@apple.com"],
                "contact_email": "anand@apple.com",
                "contact_phone": "+91 98765 12003",
            },
            {
                "key": "tanishq",
                "name": "Tanishq Jewellery",
                "category": "Jewellery",
                "zone": "A",
                "floor": 2,
                "unit_number": "A-210",
                "manager": users["meena@tanishq.com"],
                "contact_email": "meena@tanishq.com",
                "contact_phone": "+91 98765 12004",
            },
            {
                "key": "mcdonalds",
                "name": "McDonald's",
                "category": "Food & Beverage",
                "zone": "D",
                "floor": 0,
                "unit_number": "D-001",
                "manager": users["suresh@mcdonalds.com"],
                "contact_email": "suresh@mcdonalds.com",
                "contact_phone": "+91 98765 12005",
            },
        ]

        tenants = {}
        for spec in tenant_specs:
            tenant = Tenant(
                property_id=mall_property.id,
                name=spec["name"],
                category=spec["category"],
                zone=spec["zone"],
                floor=spec["floor"],
                unit_number=spec["unit_number"],
                manager_user_id=spec["manager"].id,
                pos_system_type="Cloud POS",
                inventory_system_type="RetailMind Sync",
                is_active=True,
                contact_phone=spec["contact_phone"],
                contact_email=spec["contact_email"],
            )
            db.session.add(tenant)
            tenants[spec["key"]] = tenant

        db.session.flush()

        agent_config = AgentConfiguration(property_id=mall_property.id, notification_email=mall_admin.email)
        db.session.add(agent_config)

        inventory_items = []

        def add_inventory_item(
            tenant_key,
            sku_id,
            product_name,
            category,
            brand,
            color,
            size,
            stock_level,
            reorder_threshold,
            unit_price,
            cost_price,
            sku_criticality,
            srs_score,
            supplier_name=None,
            supplier_email=None,
        ):
            tenant = tenants[tenant_key]
            default_supplier_name, default_supplier_email = _supplier_defaults(brand)
            item = InventoryItem(
                sku_id=sku_id,
                tenant_id=tenant.id,
                property_id=mall_property.id,
                product_name=product_name,
                category=category,
                brand=brand,
                color=color,
                size=size,
                stock_level=stock_level,
                reorder_threshold=reorder_threshold,
                unit_price=unit_price,
                cost_price=cost_price,
                last_restocked=now - timedelta(days=rng.randint(1, 21)),
                supplier_name=supplier_name or default_supplier_name,
                supplier_email=supplier_email or default_supplier_email,
                supplier_lead_time_hours=24,
                sku_criticality=sku_criticality,
                srs_score=srs_score,
                srs_last_computed=now - timedelta(hours=rng.randint(2, 36)),
            )
            db.session.add(item)
            inventory_items.append(item)

        add_inventory_item("zara", "ZARA-KUR-001", "Floral Anarkali Kurta", "Fashion", "Zara", "Blue", "M", 14, 10, 2999, 1200, "high", 0.72, "Zara India Distribution", "supply@zaraindia.com")
        add_inventory_item("zara", "ZARA-KUR-002", "Straight Fit Kurta Set", "Fashion", "Zara", "Pink", "S", 8, 12, 3499, 1400, "high", 0.81)
        add_inventory_item("zara", "ZARA-DRS-001", "Maxi Wrap Dress", "Fashion", "Zara", "Black", "L", 22, 8, 4499, 1800, "medium", 0.35)
        add_inventory_item("zara", "ZARA-DRS-002", "Flared Midi Dress", "Fashion", "Zara", "Red", "XS", 5, 8, 3999, 1600, "high", 0.88)
        add_inventory_item("zara", "ZARA-TRS-001", "High Waist Trousers", "Fashion", "Zara", "Beige", "M", 18, 10, 2299, 900, "low", 0.22)
        add_inventory_item("zara", "ZARA-JKT-001", "Denim Jacket", "Fashion", "Zara", "Indigo", "L", 11, 10, 5999, 2400, "medium", 0.51)
        add_inventory_item("zara", "ZARA-BLZ-001", "Formal Blazer", "Fashion", "Zara", "Charcoal", "S", 7, 10, 7499, 3000, "high", 0.76)
        add_inventory_item("zara", "ZARA-SCF-001", "Silk Scarf", "Fashion", "Zara", "Multicolor", "Free Size", 30, 15, 1499, 500, "low", 0.18)

        add_inventory_item("nike", "NIKE-RUN-001", "Air Zoom Pegasus 40", "Sportswear", "Nike", "Black/White", "UK8", 12, 10, 10495, 4200, "high", 0.79)
        add_inventory_item("nike", "NIKE-RUN-002", "React Infinity Run Flyknit", "Sportswear", "Nike", "Blue/Silver", "UK9", 6, 10, 11495, 4600, "high", 0.86)
        add_inventory_item("nike", "NIKE-BKT-001", "Air Jordan 1 Retro", "Sportswear", "Nike", "Red/Black", "UK7", 4, 8, 12995, 5200, "critical", 0.92)
        add_inventory_item("nike", "NIKE-TRN-001", "Free Metcon 4 Training Shoe", "Sportswear", "Nike", "Grey", "UK10", 20, 8, 8495, 3400, "medium", 0.40)
        add_inventory_item("nike", "NIKE-APL-001", "Dri-FIT Running T-Shirt", "Sportswear", "Nike", "White", "L", 35, 20, 1995, 800, "low", 0.15)
        add_inventory_item("nike", "NIKE-APL-002", "Pro Training Shorts", "Sportswear", "Nike", "Black", "M", 28, 15, 1795, 720, "low", 0.19)
        add_inventory_item("nike", "NIKE-BAG-001", "Brasilia Training Bag", "Sportswear", "Nike", "Black/Red", "One Size", 9, 10, 3495, 1400, "medium", 0.65)
        add_inventory_item("nike", "NIKE-CAP-001", "Dri-FIT Club Cap", "Sportswear", "Nike", "Navy", "One Size", 40, 15, 995, 400, "low", 0.12)

        add_inventory_item("apple", "AAPL-IPH-001", "iPhone 16 128GB", "Electronics", "Apple", "Black Titanium", "N/A", 8, 5, 79900, 65000, "critical", 0.77)
        add_inventory_item("apple", "AAPL-IPH-002", "iPhone 16 Plus 256GB", "Electronics", "Apple", "White", "N/A", 5, 5, 94900, 77000, "critical", 0.83)
        add_inventory_item("apple", "AAPL-MBA-001", "MacBook Air M3 8GB 256GB", "Electronics", "Apple", "Midnight", "13-inch", 4, 3, 114900, 92000, "critical", 0.68)
        add_inventory_item("apple", "AAPL-APD-001", "AirPods Pro (2nd Gen)", "Electronics", "Apple", "White", "N/A", 15, 8, 24900, 18000, "high", 0.55)
        add_inventory_item("apple", "AAPL-IPD-001", "iPad (10th Gen) 64GB", "Electronics", "Apple", "Blue", "10.9-inch", 6, 4, 44900, 36000, "high", 0.62)
        add_inventory_item("apple", "AAPL-AWT-001", "Apple Watch Series 10 GPS", "Electronics", "Apple", "Silver Aluminium", "42mm", 10, 6, 41900, 33000, "high", 0.49)

        add_inventory_item("tanishq", "TNSQ-GLD-001", "22K Gold Jhumka Earrings", "Jewellery", "Tanishq", "Gold", "Standard", 8, 5, 18500, 14800, "high", 0.58)
        add_inventory_item("tanishq", "TNSQ-GLD-002", "Diamond Pendant Necklace 18K", "Jewellery", "Tanishq", "Gold/White", "18 inch", 4, 3, 42000, 33600, "critical", 0.74)
        add_inventory_item("tanishq", "TNSQ-SLV-001", "Sterling Silver Kada Bangle Set", "Jewellery", "Tanishq", "Silver", "2.4", 12, 6, 8900, 6200, "medium", 0.38)
        add_inventory_item("tanishq", "TNSQ-GLD-003", "22K Gold Chain 10 grams", "Jewellery", "Tanishq", "Gold", "20 inch", 5, 4, 62000, 49600, "critical", 0.69)
        add_inventory_item("tanishq", "TNSQ-DIA-001", "Diamond Solitaire Ring 0.25ct", "Jewellery", "Tanishq", "Gold", "13", 3, 2, 55000, 44000, "critical", 0.81)

        add_inventory_item("mcdonalds", "MCD-CMB-001", "McAloo Tikki Combo Meal Kit", "Food & Beverage", "McDonald's India", "N/A", "Standard", 80, 30, 199, 90, "medium", 0.44)
        add_inventory_item("mcdonalds", "MCD-CMB-002", "Maharaja Mac Combo Meal Kit", "Food & Beverage", "McDonald's India", "N/A", "Standard", 65, 25, 329, 140, "medium", 0.38)
        add_inventory_item("mcdonalds", "MCD-BVG-001", "McFlurry Oreo Ingredient Pack", "Food & Beverage", "McDonald's India", "N/A", "Large", 45, 20, 179, 75, "low", 0.21)

        db.session.flush()

        for idx in range(100):
            item = rng.choice(inventory_items)
            bias = rng.random()
            day_offset = rng.randint(0, 6)

            if bias < 0.65:
                hour = rng.randint(18, 21)
            elif bias < 0.85:
                hour = rng.randint(10, 12)
            else:
                hour = rng.randint(13, 22)

            sale_timestamp = (now - timedelta(days=day_offset)).replace(
                hour=hour,
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
                microsecond=0,
            )

            if sale_timestamp.weekday() >= 5:
                units_sold = rng.randint(2, 5)
            else:
                units_sold = rng.randint(1, 2)

            db.session.add(
                SalesVelocity(
                    sku_id=item.sku_id,
                    tenant_id=item.tenant_id,
                    property_id=mall_property.id,
                    units_sold=units_sold,
                    sale_timestamp=sale_timestamp,
                    zone_id=item.tenant.zone,
                    transaction_id=f"TXN-{sale_timestamp.strftime('%Y%m%d')}-{idx + 1:04d}",
                )
            )

        floor_map = {"A": 1, "B": 2, "C": 1, "D": 0, "E": -1}
        zones = ["A", "B", "C", "D", "E"]

        for _ in range(200):
            zone = rng.choice(zones)
            day_offset = rng.randint(0, 6)

            if zone == "D" and rng.random() < 0.60:
                hour = rng.randint(12, 14)
            elif zone == "A" and rng.random() < 0.55:
                hour = rng.randint(17, 20)
            else:
                hour = rng.randint(10, 22)

            traffic_timestamp = (now - timedelta(days=day_offset)).replace(
                hour=hour,
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
                microsecond=0,
            )

            if zone == "D":
                low, high = (800, 1200) if 12 <= hour <= 14 else (450, 850)
            elif zone == "A":
                low, high = (600, 900) if 17 <= hour <= 20 else (350, 650)
            elif zone == "B":
                low, high = (400, 700)
            elif zone == "C":
                low, high = (300, 500)
            else:
                low, high = (250, 450)

            count = rng.randint(low, high)
            if traffic_timestamp.weekday() >= 5:
                count = int(count * rng.uniform(1.3, 1.5))

            db.session.add(
                FootTraffic(
                    property_id=mall_property.id,
                    zone_id=zone,
                    floor=floor_map[zone],
                    count=count,
                    timestamp=traffic_timestamp,
                    data_source="simulator",
                )
            )

        equipment_records = [
            Equipment(
                property_id=mall_property.id,
                equipment_name="Escalator E-01",
                equipment_type="escalator",
                zone="A",
                floor=1,
                installation_date=date.today() - timedelta(days=4 * 365),
                expected_lifetime_years=20,
                last_serviced=now - timedelta(days=90),
                manufacturer="Otis",
                model_number="Otis-2000",
                is_active=True,
                fps_score=0.35,
                fps_last_computed=now - timedelta(hours=8),
            ),
            Equipment(
                property_id=mall_property.id,
                equipment_name="Escalator E-02",
                equipment_type="escalator",
                zone="B",
                floor=2,
                installation_date=date.today() - timedelta(days=7 * 365),
                expected_lifetime_years=20,
                last_serviced=now - timedelta(days=240),
                manufacturer="KONE",
                model_number="KONE-EcoSpace",
                is_active=True,
                fps_score=0.71,
                fps_last_computed=now - timedelta(hours=4),
            ),
            Equipment(
                property_id=mall_property.id,
                equipment_name="HVAC Unit H-01",
                equipment_type="hvac",
                zone="C",
                floor=4,
                installation_date=date.today() - timedelta(days=3 * 365),
                expected_lifetime_years=15,
                last_serviced=now - timedelta(days=60),
                manufacturer="Blue Star",
                model_number="BS-Commercial-2021",
                is_active=True,
                fps_score=0.28,
                fps_last_computed=now - timedelta(hours=6),
            ),
            Equipment(
                property_id=mall_property.id,
                equipment_name="Generator G-01",
                equipment_type="generator",
                zone="E",
                floor=-1,
                installation_date=date.today() - timedelta(days=5 * 365),
                expected_lifetime_years=20,
                last_serviced=now - timedelta(days=30),
                manufacturer="Cummins",
                model_number="Cummins-125kVA",
                is_active=True,
                fps_score=0.22,
                fps_last_computed=now - timedelta(hours=3),
            ),
            Equipment(
                property_id=mall_property.id,
                equipment_name="Fire Alarm System F-01",
                equipment_type="fire_alarm",
                zone="All Zones",
                floor=0,
                installation_date=date.today() - timedelta(days=2 * 365),
                expected_lifetime_years=10,
                last_serviced=now - timedelta(days=14),
                manufacturer="Honeywell",
                model_number="Honeywell-FX-Series",
                is_active=True,
                fps_score=0.18,
                fps_last_computed=now - timedelta(hours=2),
            ),
        ]
        db.session.add_all(equipment_records)
        db.session.flush()

        equipment_map = {equipment.equipment_name: equipment for equipment in equipment_records}

        normal_metric_map = {
            "escalator": ("vibration_hz", 46.0, 54.0, 50.0, 2.0),
            "hvac": ("temperature_celsius", 19.0, 24.0, 21.5, 1.2),
            "generator": ("current_amps", 115.0, 160.0, 137.5, 10.0),
            "fire_alarm": ("noise_db", 35.0, 52.0, 43.5, 4.0),
        }

        escalator_e2 = equipment_map["Escalator E-02"]
        start_time = now - timedelta(hours=48)

        for idx in range(120):
            timestamp = start_time + timedelta(minutes=idx * 24)
            if idx < 80:
                value = round(rng.uniform(45.0, 55.0), 2)
                z_score = round((value - 50.0) / 2.0, 2)
                anomaly_flag = False
                anomaly_score = round(min(0.45, abs(z_score) / 6.0), 2)
            else:
                progress = (idx - 80) / 39
                value = round(58.5 + (16.5 * progress) + rng.uniform(-0.35, 0.35), 2)
                z_score = round((value - 50.0) / 3.0, 2)
                anomaly_flag = True
                anomaly_score = round(min(1.0, 0.65 + (0.35 * progress)), 2)

            db.session.add(
                SensorReading(
                    equipment_id=escalator_e2.id,
                    property_id=mall_property.id,
                    metric_name="vibration_hz",
                    metric_value=value,
                    timestamp=timestamp,
                    anomaly_flag=anomaly_flag,
                    anomaly_score=anomaly_score,
                    z_score=z_score,
                )
            )

        for equipment in equipment_records:
            if equipment.equipment_name == "Escalator E-02":
                continue

            metric_name, low, high, baseline, std_dev = normal_metric_map[equipment.equipment_type]
            for _ in range(95):
                value = round(rng.uniform(low, high), 2)
                timestamp = now - timedelta(hours=rng.uniform(0, 48))
                z_score = round((value - baseline) / std_dev, 2)

                db.session.add(
                    SensorReading(
                        equipment_id=equipment.id,
                        property_id=mall_property.id,
                        metric_name=metric_name,
                        metric_value=value,
                        timestamp=timestamp,
                        anomaly_flag=False,
                        anomaly_score=round(min(0.35, abs(z_score) / 10.0), 2),
                        z_score=z_score,
                    )
                )

        nike_tenant = tenants["nike"]
        zara_tenant = tenants["zara"]
        tanishq_tenant = tenants["tanishq"]

        campaign_nike = Campaign(
            property_id=mall_property.id,
            tenant_id=nike_tenant.id,
            campaign_name="Nike Weekend Sportswear Blast",
            campaign_copy=(
                "Gear up this weekend! Exclusive deals on Nike performance footwear at Zone B, Floor 2. "
                "Up to 20% off on select running shoes today only at Phoenix Marketcity."
            ),
            target_zone="B",
            target_audience_description="Athleisure and running enthusiasts",
            opportunity_score=0.88,
            status="active",
            channel="digital_signage",
            weather_context="Clear/Sunny",
            event_context="Weekend Rush",
            created_at=now - timedelta(hours=3),
            activated_at=now - timedelta(hours=2),
            impressions=1240,
            clicks=187,
            conversions=23,
            revenue_attributed=48350.0,
            created_by_agent=True,
            gemini_prompt_used="Promote high intent running footwear based on traffic and weather context.",
        )

        campaign_zara = Campaign(
            property_id=mall_property.id,
            tenant_id=zara_tenant.id,
            campaign_name="Zara Fashion Week Collection",
            campaign_copy=(
                "The new Zara Spring Collection has arrived at Zone A! Explore 50+ new styles in our flagship "
                "store from ethnic fusion to contemporary western wear."
            ),
            target_zone="A",
            target_audience_description="Fashion forward young professionals and families",
            opportunity_score=0.79,
            status="opportunity",
            channel="push_notification",
            weather_context="Partly Cloudy",
            event_context="Spring Fashion",
            created_at=now - timedelta(minutes=45),
            impressions=0,
            clicks=0,
            conversions=0,
            revenue_attributed=0.0,
            created_by_agent=True,
            gemini_prompt_used="Capitalize on evening fashion traffic with localized push messaging.",
        )

        campaign_tanishq = Campaign(
            property_id=mall_property.id,
            tenant_id=tanishq_tenant.id,
            campaign_name="Tanishq Dhanteras Dhamaka",
            campaign_copy="Celebrate Dhanteras with exclusive jewellery collections and festive offers.",
            target_zone="A",
            target_audience_description="Festival shoppers and high value gifting customers",
            opportunity_score=0.94,
            status="completed",
            channel="sms",
            weather_context="Clear/Sunny",
            event_context="Dhanteras Festival",
            created_at=now - timedelta(days=31),
            activated_at=now - timedelta(days=30),
            expires_at=now - timedelta(days=28),
            impressions=8500,
            clicks=1240,
            conversions=89,
            revenue_attributed=324750.0,
            created_by_agent=True,
            gemini_prompt_used="Festive buying spike in jewellery category with premium buyer segments.",
        )

        db.session.add_all([campaign_nike, campaign_zara, campaign_tanishq])
        db.session.flush()

        action_1 = AgentAction(
            property_id=mall_property.id,
            mission_type="inventory",
            action_type="restock_request",
            description=(
                "Nike Air Jordan 1 Retro in Zone B has critically low stock (4 units). SRS score 0.92 exceeds "
                "threshold. Recommend immediate restock of 30 units from Nike India Distribution."
            ),
            entity_id="NIKE-BKT-001",
            score=0.92,
            status="pending",
            agent_reasoning=(
                "Current stock level of 4 units with high sales velocity (2.3 units/hour during peak) and "
                "24-hour supplier lead time creates critical risk of stockout within 2 hours. Weekend foot "
                "traffic multiplier of 1.4x further accelerates depletion."
            ),
            created_at=now - timedelta(minutes=30),
        )

        action_2 = AgentAction(
            property_id=mall_property.id,
            mission_type="campaign",
            action_type="campaign_activated",
            description=(
                "Campaign 'Nike Weekend Sportswear Blast' auto-activated for Zone B based on high foot traffic "
                "(920 visitors/hour) and clear weather conditions."
            ),
            entity_id=f"Campaign {campaign_nike.id} (Nike)",
            score=0.88,
            status="auto_executed",
            created_at=now - timedelta(hours=2),
            resolved_at=now - timedelta(hours=2),
        )

        action_3 = AgentAction(
            property_id=mall_property.id,
            mission_type="facility",
            action_type="anomaly_detected",
            description=(
                "Escalator E-02 in Zone B showing sustained vibration anomaly. 40 consecutive readings above "
                "2.5 standard deviations. FPS score 0.71 exceeds threshold 0.65. Preventive maintenance recommended."
            ),
            entity_id="Escalator E-02",
            score=0.71,
            status="pending",
            agent_reasoning=(
                "Vibration readings trending from 58Hz to 75Hz over last 4 hours against baseline of 50Hz. "
                "Z-scores between 2.8 and 6.2. Equipment age factor 0.35 combined with anomaly rate 0.67 "
                "indicates imminent failure risk."
            ),
            created_at=now - timedelta(hours=1),
        )

        action_4 = AgentAction(
            property_id=mall_property.id,
            mission_type="inventory",
            action_type="restock_request",
            description=(
                "Zara Flared Midi Dress in Red/XS has 5 units remaining. SRS 0.88 exceeds threshold."
            ),
            entity_id="ZARA-DRS-002",
            score=0.88,
            status="approved",
            approved_by_user_id=mall_admin.id,
            created_at=now - timedelta(hours=5),
            resolved_at=now - timedelta(hours=3),
        )

        action_5 = AgentAction(
            property_id=mall_property.id,
            mission_type="campaign",
            action_type="campaign_opportunity",
            description=(
                "Campaign opportunity identified for Zara Fashion in Zone A. High foot traffic with seasonal fashion demand."
            ),
            entity_id="Zara Zone A",
            score=0.79,
            status="pending",
            created_at=now - timedelta(minutes=45),
        )

        db.session.add_all([action_1, action_2, action_3, action_4, action_5])

        notifications_data = [
            ("Critical Nike Stock Risk", "NIKE-BKT-001 has only 4 units left. Restock recommendation pending approval.", "inventory_alert", "critical", False, "/inventory"),
            ("Zara Restock Approved", "ZARA-DRS-002 restock request was approved and forwarded to supplier.", "inventory_alert", "info", True, "/inventory"),
            ("Campaign Opportunity Detected", "Zara Zone A shows high evening demand. Suggested campaign is ready for review.", "campaign_opportunity", "warning", False, "/campaigns"),
            ("Nike Campaign Performing", "Nike Weekend Sportswear Blast reached 1240 impressions and 23 conversions.", "campaign_opportunity", "info", True, "/campaigns"),
            ("Escalator Vibration Alert", "Escalator E-02 anomaly sustained. Preventive maintenance recommended.", "facility_alert", "critical", False, "/facility"),
            ("Generator Health Stable", "Generator G-01 diagnostics are within normal threshold for the last 24 hours.", "facility_alert", "info", True, "/facility"),
            ("Agent Action Pending", "One inventory action and one facility anomaly require your approval.", "agent_action", "warning", False, "/agent-actions"),
            ("Nightly Agent Summary", "4 autonomous checks completed overnight with 2 actionable outcomes.", "agent_action", "info", True, "/agent-actions"),
            ("System Backup Complete", "Daily backup completed successfully at 03:00 AM IST.", "system", "info", True, "/settings"),
            ("Subscription Active", "Professional plan is active. Next billing cycle starts next month.", "billing", "info", False, "/billing"),
        ]

        for title, message, notif_type, severity, is_read, action_url in notifications_data:
            db.session.add(
                Notification(
                    user_id=mall_admin.id,
                    property_id=mall_property.id,
                    title=title,
                    message=message,
                    notification_type=notif_type,
                    severity=severity,
                    is_read=is_read,
                    action_url=action_url,
                    created_at=now - timedelta(minutes=rng.randint(5, 300)),
                )
            )

        period_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)

        subscription = Subscription(
            property_id=mall_property.id,
            plan_name="professional",
            price_inr=149999.0,
            billing_cycle="monthly",
            status="active",
            current_period_start=period_start,
            current_period_end=next_month - timedelta(seconds=1),
        )
        db.session.add(subscription)

        db.session.commit()

        print("============================================================")
        print("  RetailMind — Database Seeded Successfully!")
        print("============================================================")
        print("  Superadmin    : superadmin@retailmind.ai  / SuperAdmin@123")
        print("  Mall Admin    : rajan@phoenixmall.com     / MallAdmin@123")
        print("  Marketing Mgr : anika@phoenixmall.com     / Marketing@123")
        print("  Facility Mgr  : sureshp@phoenixmall.com   / Facility@123")
        print("  Store Manager : priya@zara.com            / StoreManager@123")
        print("  Store Manager : vikram@nike.com           / StoreManager@123")
        print("  Store Manager : anand@apple.com           / StoreManager@123")
        print("  Store Manager : meena@tanishq.com         / StoreManager@123")
        print("  Store Manager : suresh@mcdonalds.com      / StoreManager@123")
        print("------------------------------------------------------------")
        print("  Application running at: http://localhost:5000")
        print("============================================================")
    except Exception:
        db.session.rollback()
        raise
