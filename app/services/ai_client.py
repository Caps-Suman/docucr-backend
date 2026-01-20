from openai import AsyncOpenAI
import os

openai_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
