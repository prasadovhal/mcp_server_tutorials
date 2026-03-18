"""
Authentication (JWT) : security
Rate Limiting : 100 requests / minute
Async APIs : asynchronous programming.handle thousands of requests, better performance
Production-like Architecture (cache + structure)

"""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import redis
import httpx
import asyncio

# =========================
# CONFIG
# =========================
SECRET_KEY = "mysecretkey"
ALGORITHM = "HS256"

# =========================
# APP INIT
# =========================
app = FastAPI()

# =========================
# RATE LIMITING (Step 16)
# =========================
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: HTTPException(429, "Too many requests"))
app.add_middleware(SlowAPIMiddleware)

# =========================
# REDIS CACHE (Step 18)
# =========================
cache = redis.Redis(host="localhost", port=6379, decode_responses=True)

# =========================
# AUTH SETUP (Step 15)
# =========================
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

fake_user_db = {
    "prasad": {
        "username": "prasad",
        "password": pwd_context.hash("1234")
    }
}

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    return decode_token(token)

# =========================
# AUTH ROUTES
# =========================
@app.post("/login")
def login(username: str, password: str):
    user = fake_user_db.get(username)

    if not user or not verify_password(password, user["password"]):
        raise HTTPException(401, "Invalid credentials")

    token = create_token({"username": username})
    return {"access_token": token}

# =========================
# ASYNC EXTERNAL CALL (Step 17)
# =========================
async def fetch_external_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://jsonplaceholder.typicode.com/todos/1")
        return response.json()

# =========================
# PROTECTED ROUTE
# =========================
@app.get("/protected")
@limiter.limit("5/minute")
async def protected_route(
    request: Request,
    user=Depends(get_current_user)
):
    return {"message": "Protected access", "user": user}

# =========================
# CACHE + ASYNC + RATE LIMIT
# =========================
@app.get("/data")
@limiter.limit("10/minute")
async def get_data(request: Request):

    # Check cache first
    cached = cache.get("external_data")
    if cached:
        return {"source": "cache", "data": cached}

    # Async API call
    data = await fetch_external_data()

    # Store in cache
    cache.set("external_data", str(data), ex=60)

    return {"source": "api", "data": data}

# =========================
# SIMULATED AI ENDPOINT
# =========================
@app.post("/ai")
@limiter.limit("3/minute")
async def ai_endpoint(request: Request, prompt: str, user=Depends(get_current_user)):

    # simulate async model processing
    await asyncio.sleep(1)

    return {
        "user": user,
        "response": f"AI processed: {prompt}"
    }