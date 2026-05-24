from app.routes.auth import auth_bp
from app.routes.agent import agent_bp
from app.routes.analytics import analytics_bp
from app.routes.api import api_bp
from app.routes.campaigns import campaigns_bp
from app.routes.dashboard import dashboard_bp
from app.routes.facility import facility_bp
from app.routes.inventory import inventory_bp
from app.routes.notifications import notifications_bp
from app.routes.onboarding import onboarding_bp
from app.routes.public import public_bp
from app.routes.settings import settings_bp
from app.routes.shopper import shopper_bp
from app.routes.superadmin import superadmin_bp
from app.routes.pwa import pwa_bp
from app.routes.push import push_bp

__all__ = [
	"public_bp",
	"auth_bp",
	"onboarding_bp",
	"dashboard_bp",
	"notifications_bp",
	"inventory_bp",
	"campaigns_bp",
	"facility_bp",
	"analytics_bp",
	"agent_bp",
	"shopper_bp",
	"settings_bp",
	"api_bp",
	"superadmin_bp",
	"pwa_bp",
	"push_bp",
]
