from openai import AsyncOpenAI
import os

openai_client = AsyncOpenAI(
    openai_api_key=os.getenv("OPENAI_API_KEY")
)
