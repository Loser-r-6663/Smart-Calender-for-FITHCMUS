import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_ENCRYPTION_KEY = os.getenv("SUPABASE_ENCRYPTION_KEY")


class BaseSupabaseClient:
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_PUBLIC_KEY")
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {access_token or self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
    
    @staticmethod
    def _raise(response: requests.Response):
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise requests.HTTPError(
                f"{response.status_code} {response.reason}: {detail}",
                response=response,
            )
