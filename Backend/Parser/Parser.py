import os
import random
import time
import traceback
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors

from Backend.Regulation.RawTask import RawTask
from Backend.Regulation.ExtractedTask import ExtractedTask


class LLMParser:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
            api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.config = types.GenerateContentConfig(
            system_instruction=(
                "Bạn là trợ lý thông minh chuyên trích xuất dữ liệu từ các thông báo của trường đại học Khoa học tự nhiên. "
                "Tất cả các mốc thời gian (datetime) trích xuất được PHẢI LUÔN thuộc múi giờ GMT+7 (Việt Nam, UTC+7). "
                "Chỉ trích xuất các thông tin có bằng chứng rõ ràng trong văn bản, không tự suy diễn."
            ),
            response_mime_type="application/json",
            response_schema=list[ExtractedTask],
        )
    
    @staticmethod
    def retry_request(func, max_retries = 5):
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
    
    def parse(self, raw_task: RawTask, max_retries = 5) -> list[ExtractedTask]:
        """Parse the raw task content and extract structured information."""
        response = self.retry_request(
            lambda: self.client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=f"Trích xuất thông tin sự kiện từ bài viết sau, một bài viết có thể có một hoặc nhiều sự kiện:\n{raw_task!r}",
                config=self.config
            ).parsed,
            max_retries=max_retries
        )
        return response

Parser = LLMParser()
