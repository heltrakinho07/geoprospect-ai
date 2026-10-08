import os
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from dotenv import load_dotenv

load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET", "DEVELOPMENT_ONLY_CHANGE_ME_32_BYTES_LONG")
APP_ENV = os.getenv("APP_ENV", "development")
JWT_ISSUER = "geoprospect-ai"
ALGORITHM = "HS256"
_hasher = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)

def check_configuration() -> None:
    if APP_ENV == "production" and (len(JWT_SECRET) < 32 or any(s in JWT_SECRET for s in ("CHANGE_ME","DEVELOPMENT_ONLY","REPLACE_WITH"))):
        raise RuntimeError("Production requires a random private JWT_SECRET (32+ characters)")
    if APP_ENV == "production" and not os.getenv("DATABASE_URL", "").startswith("postgresql"):
        raise RuntimeError("Production requires PostgreSQL")

def hash_password(password: str) -> str:
    return _hasher.hash(password)

def verify_password(encoded: str, candidate: str) -> bool:
    try:
        return _hasher.verify(encoded, candidate)
    except (VerifyMismatchError, VerificationError):
        return False

def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub":user_id, "iat":now, "nbf":now, "exp":now+timedelta(hours=8), "iss":JWT_ISSUER},JWT_SECRET,algorithm=ALGORITHM)

def decode_token(token: str) -> str:
    claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM], issuer=JWT_ISSUER, options={"require":["exp","sub","iss","iat"]})
    return str(claims["sub"])
