from __future__ import annotations

import requests


def update_password(access_token: str, password: str) -> None:
    """Update the signed-in account without modifying crawler-branch code."""
    from Database.auth import AUTH_URL, SUPABASE_PUBLIC_KEY
    from Database.Repository.user_repository import UserRepository

    response = requests.put(
        f"{AUTH_URL}/user",
        headers={
            "apikey": SUPABASE_PUBLIC_KEY,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"password": password},
        timeout=30,
    )
    UserRepository._raise(response)
