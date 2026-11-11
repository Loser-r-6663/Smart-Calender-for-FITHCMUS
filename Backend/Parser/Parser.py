import os
import random
import time
import traceback
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
from google.genai.types import GenerateContentResponse

from Backend.Regulation.Task import RawTask, ExtractedTask


class LLMParser:
    def __init__(self):
        load_dotenv()
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedTask,
        )
    
    @staticmethod
    def retry_request(func, max_retries = 5) -> GenerateContentResponse:
        """Retry a request in case of API errors with exponential backoff."""
        for attempt in range(max_retries + 1):
            try:
                return func()
            
            except errors.APIError as exc:
                if exc.code not in (429, 503) or attempt == max_retries:
                    traceback.print_exc()
                
                delay = min(2 ** attempt, 32) + random.uniform(0, 1)
                print(f"⚠️ Lỗi {exc.code}, thử lại lần {attempt + 1}/{max_retries} sau {delay:.1f}s...")
                time.sleep(delay)
    
    def parse(self, raw_task: RawTask, max_retries = 5) -> ExtractedTask:
        """Parse the raw task content and extract structured information."""
        response = self.retry_request(
            lambda: self.client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=f"Trích xuất thông tin từ bài viết sau:\n{raw_task!r}",
                config=self.config
            ),
            max_retries=max_retries
        )
        return response.parsed

Parser = LLMParser()
