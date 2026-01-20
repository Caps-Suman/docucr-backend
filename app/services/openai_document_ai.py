import json
import io
import base64
from typing import List, Dict, Any
from pdf2image import convert_from_bytes
from PIL import Image
from openai import OpenAIError
import re


class OpenAIDocumentAI:
    MAX_PAGES_PER_REQUEST = 4  # hard limit for stability

    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    # ---------- helpers ----------

    def _extract_json_from_response(self, response) -> Dict[str, Any]:
        """
        Correctly extract JSON from OpenAI Responses API output objects.
        """
        for message in response.output:
            for block in message.content:
                if block.type == "output_text":
                    text = (block.text or "").strip()
                    if not text:
                        continue

                    # Strip markdown fences if present
                    text = re.sub(r"^```json|```$", "", text, flags=re.MULTILINE).strip()

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        raise RuntimeError(
                            f"Invalid JSON from model.\nText:\n{text}"
                        ) from e

        raise RuntimeError(
            f"No JSON output found. Full response: {response}"
        )

    def _encode_image(self, image: Image.Image) -> str:
        if image.mode != "RGB":
            image = image.convert("RGB")

        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _pdf_to_images(self, file_bytes: bytes) -> List[str]:
        pages = convert_from_bytes(file_bytes)
        return [self._encode_image(p) for p in pages]

    def _chunk(self, items: List[str], size: int):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    # ---------- main ----------
    async def analyze(
        self,
        file_bytes: bytes,
        filename: str,
        schemas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        images: List[str] = []
        if filename.lower().endswith(".pdf"):
            images = self._pdf_to_images(file_bytes)

        system_prompt = ('''
                You are a medical document classification and extraction engine.

        DEFINITIONS:
        - A "page" refers to a single input image.
        - A "document" is one or more consecutive pages that belong together.
        - Each page MUST belong to exactly ONE document.
        - Each document MUST have exactly ONE document type.

        ALLOWED DOCUMENT TYPES:
        Use ONLY the document types defined in the schemas.
        Do NOT invent new types.

        STRICT RULES (NON-NEGOTIABLE):
        1. For any given page, assign ONLY ONE document type.
        2. NEVER produce more than one document type for the same page.
        3. If multiple pages belong to the same document, MERGE them into a single document.
        4. NEVER duplicate the same document more than once.
        5. If a document spans multiple pages, output it ONCE.
        6. If information is missing, use null — DO NOT duplicate documents.
        7. The output MUST be deterministic and deduplicated.

        FIELD EXTRACTION RULES:
        - Extract ONLY fields defined in the schema for that document type.
        - Output ALL fields for a document in a SINGLE object.
        - Do NOT repeat the same field multiple times.
        - Normalize field names exactly as defined in the schema.

        OUTPUT FORMAT (STRICT):
        Return a JSON object with this exact structure:

        {
        "documents": [
            {
            "type_name": "<DOCUMENT_TYPE>",
            "pages": [<page_numbers>],
            "fields": {
                "<field_name>": "<value or null>"
            }
            }
        ]
        }

        IMPORTANT:
        - NEVER return nested "documents" arrays.
        - NEVER return duplicate documents.
        - NEVER return arrays of fields — fields MUST be a single object.
        - If a page was classified once, DO NOT classify it again.

        OUTPUT JSON ONLY.
        NO explanations.
        NO markdown.
'''
        )

        results: List[Dict[str, Any]] = []

        try:
            for page_group in self._chunk(images, self.MAX_PAGES_PER_REQUEST):
                user_content = [
                    {"type": "input_text", "text": "Analyze this document"}
                ]

                for img in page_group:
                    user_content.append({
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{img}"
                    })

                response = await self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": [{"type": "input_text", "text": system_prompt}]
                        },
                        {
                            "role": "user",
                            "content": user_content
                        }
                    ],
                    max_output_tokens=1200
                )

                chunk_result = self._extract_json_from_response(response)
                results.append(chunk_result)

        except OpenAIError as e:
            raise RuntimeError(f"OpenAI request failed: {e}")

        # Merge chunk results (simple merge strategy)
        if len(results) == 1:
            return results[0]

        return {
            "documents": results
        }
