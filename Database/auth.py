import os
import requests
from dotenv import load_dotenv

from Database.Repository.user_repository import UserRepository

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLIC_KEY = os.getenv("SUPABASE_PUBLIC_KEY")
AUTH_URL = f"{SUPABASE_URL}/auth/v1"


def email_check(username: str) -> str:
    """Check if the username is a valid email."""
    if "@" in username: return username
    raise ValueError("Username must be a valid email address. Please provide a valid email.")

def sign_up(username: str, password: str):
    """Create a new user. Returns { id, email, ... }."""
    response = requests.post(
        f"{AUTH_URL}/signup",
        headers={
            "apikey": SUPABASE_PUBLIC_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email_check(username),
            "password": password,
        },
        timeout=30,
    )
    UserRepository._raise(response)
    access_token, user = sign_in(username, password)
    
    database = UserRepository(access_token=access_token)
    database.save_user(user)
    return access_token, user

def sign_in(username: str, password: str):
    """Sign in an existing user. Returns { access_token, user: { id, email, ... } }."""
    response = requests.post(
        f"{AUTH_URL}/token?grant_type=password",
        headers={
            "apikey": SUPABASE_PUBLIC_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email_check(username),
            "password": password,
        },
        timeout=30,
    )
    UserRepository._raise(response)
    auth_data = response.json()
    
    access_token: str = auth_data["access_token"]
    auth_data["user"]["username"] = auth_data["user"]["email"]
    user = UserRepository.row_to_user(auth_data["user"])
    
    database = UserRepository(access_token=access_token)
    maybe_user = database.get_user(user.id)
    if maybe_user:
        user = maybe_user
    return access_token, user

def sign_out(access_token: str):
    requests.post(
        f"{AUTH_URL}/logout",
        headers={
            "apikey": SUPABASE_PUBLIC_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )
