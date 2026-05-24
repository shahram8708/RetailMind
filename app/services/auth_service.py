from datetime import datetime, timedelta
import uuid

from app.extensions import db
from app.models.user import EmailVerificationToken, PasswordResetToken


def generate_verification_token(user_id):
    token_value = str(uuid.uuid4())
    verification = EmailVerificationToken(
        user_id=user_id,
        token=token_value,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        used=False,
    )
    db.session.add(verification)
    db.session.commit()
    return token_value


def verify_email_token(token):
    token_record = EmailVerificationToken.query.filter_by(token=token, used=False).first()
    if token_record is None:
        return None, "Invalid token"

    if token_record.expires_at < datetime.utcnow():
        return None, "Token expired"

    token_record.used = True
    token_record.user.is_verified = True
    db.session.commit()
    return token_record.user, None


def generate_password_reset_token(user_id):
    existing_tokens = PasswordResetToken.query.filter_by(user_id=user_id, used=False).all()
    for old_token in existing_tokens:
        old_token.used = True

    token_value = str(uuid.uuid4())
    reset_record = PasswordResetToken(
        user_id=user_id,
        token=token_value,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        used=False,
    )
    db.session.add(reset_record)
    db.session.commit()
    return token_value


def verify_password_reset_token(token):
    token_record = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if token_record is None:
        return None, "Invalid token"

    if token_record.expires_at < datetime.utcnow():
        return None, "Token expired"

    return token_record.user, None
