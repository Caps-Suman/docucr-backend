import os
import io
import json
import base64
import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI
from pdf2image import convert_from_bytes
from PIL import Image


class AIService:
    def __init__(self):
        self.azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        self.api_version = os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        )

        # self.client = AsyncAzureOpenAI(
        #     api_key=self.azure_api_key,
        #     api_version=self.api_version,
        #     azure_endpoint=self.endpoint
        # )
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _format_document_types(self, document_types: List[Dict[str, str]]) -> str:
        lines = []
        for dt in document_types:
            if not isinstance(dt, dict):
                continue
            name = dt.get("name", "UNKNOWN")
            desc = dt.get("description") or "No description provided"
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def _convert_to_images(self, file_content: bytes, filename: str) -> List[str]:
        if filename.lower().endswith(".pdf"):
            loop = asyncio.get_event_loop()
            pages = await loop.run_in_executor(None, convert_from_bytes, file_content)
            return [self._encode_image(p) for p in pages]

        image = Image.open(io.BytesIO(file_content))
        return [self._encode_image(image)]

    # ------------------------------------------------------------------
    # Phase 1 — Structure detection (chunked + domain aware)
    # ------------------------------------------------------------------
    async def _classify_pages_batched(
    self,
    images: List[str],
    document_types: List[Dict[str, str]],
    batch_size: int = 2
):  
        assigned_pages = {}  # page_number -> document_type

        all_pages = []
        doc_type_block = self._format_document_types(document_types)

        system_prompt = f"""
You are classifying individual medical document pages.

DOCUMENT TYPES (AUTHORITATIVE — USE DESCRIPTIONS):
{doc_type_block}

GLOBAL PAGE ASSIGNMENT RULE (ABSOLUTE — DO NOT VIOLATE):

Some pages MAY have been classified earlier.

- Any page already assigned a document type is FINAL and IMMUTABLE.
- You MUST NOT reclassify, override, or change the document type of such pages.
- You MUST NOT assign a second document type to an already-classified page.
- You MUST NOT include already-classified pages in the output again.

If you see an already-classified page:
- SKIP IT COMPLETELY
- DO NOT output it
- DO NOT reconsider it
- DO NOT question it

Violating this rule is a HARD FAILURE.

HARD CONSTRAINTS (NON-NEGOTIABLE):
- EACH page MUST be assigned EXACTLY ONE document type
- NEVER assign more than one document type to a page
- NEVER return multiple entries for the same page
- If uncertain between two types, choose the BEST match based on description

DECISION RULES:
- CPT/ICD codes, procedures, radiology, medical services → Superbill
- Totals, balances, amounts due, invoice numbers → Invoice
- Patient info only (name, DOB, insurance) → Demographics

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "pages": [
    {{
      "page": <page_number>,
      "type": "<DocumentType>",
      "patient_name": "<string|null>",
      "dob": "<YYYY-MM-DD|null>",
      "insurance": "<string|null>"
    }}
  ]
}}

DO NOT add explanations.
DO NOT add confidence.
DO NOT add extra keys.
"""

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

            user_content = [{"type": "text", "text": "Analyze the following pages."}]

            for idx, img in enumerate(batch):
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}
                })

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=512,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Fix page numbers
            for p in result.get("pages", []):
                p["page"] += i

            all_pages.extend(result.get("pages", []))

            # ✅ SHORT sleep, not 60s
            await asyncio.sleep(30)

        return all_pages
    async def safe_call(fn):
        for attempt in range(3):
            try:
                return await fn()
            except Exception as e:
                if "RateLimit" in str(e):
                    await asyncio.sleep(15 * (attempt + 1))
                else:
                    raise
        raise RuntimeError("Azure rate limit not recovered")


    def _group_pages_into_documents(self, pages: List[Dict[str, Any]]):
        documents = []
        current = None

        def signature(p):
            return (
                p["type"],
                p.get("patient_name"),
                p.get("dob"),
                p.get("insurance")
            )

        for p in sorted(pages, key=lambda x: x["page"]):
            sig = signature(p)

            if current is None or current["signature"] != sig:
                current = {
                    "type": p["type"],
                    "page_range": [p["page"], p["page"]],
                    "signature": sig
                }
                documents.append(current)
            else:
                current["page_range"][1] = p["page"]

        # cleanup
        for d in documents:
            d["page_range"] = f"{d['page_range'][0]}-{d['page_range'][1]}"
            del d["signature"]

        return documents

    # ------------------------------------------------------------------
    # Normalize & merge overlapping / adjacent documents
    # ------------------------------------------------------------------

    def _normalize_documents(self, docs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not docs:
            return []

        def parse_range(r):
            s, e = map(int, r.split("-"))
            return s, e

        # Sort by start asc, end desc (longer ranges win)
        docs_sorted = sorted(
            docs,
            key=lambda d: (parse_range(d["page_range"])[0], -parse_range(d["page_range"])[1])
        )

        page_owner = {}  # page -> doc index
        final_docs = []

        for doc in docs_sorted:
            start, end = parse_range(doc["page_range"])
            doc_type = doc["type"]

            # Check if ANY page already assigned
            overlapping = [p for p in range(start, end + 1) if p in page_owner]

            if overlapping:
                # ❌ Reject duplicate / weaker document
                continue

            # Assign ownership
            doc_index = len(final_docs)
            for p in range(start, end + 1):
                page_owner[p] = doc_index

            final_docs.append({
                "type": doc_type,
                "page_range": f"{start}-{end}"
            })

        return final_docs



    # ------------------------------------------------------------------
    # Phase 2 — Field extraction
    # ------------------------------------------------------------------

    async def _extract_fields(
        self,
        doc_type: str,
        page_range: str,
        images: List[str],
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        schema_payload = {
            "type_name": schema["type_name"],
            "fields": schema.get("fields", [])
        }
        start, end = map(int, page_range.split("-"))
        selected_images = images[start - 1:end]

        system_prompt = f"""
You are extracting structured data from a medical document.

IMPORTANT CONTEXT (DO NOT VIOLATE):
- The document has ALREADY been classified.
- The document type is FINAL and MUST NOT be changed.
- The page range provided belongs to ONE and ONLY ONE document.
- Do NOT infer, split, or reclassify documents.

DOCUMENT TYPE:
{doc_type}

AUTHORITATIVE PAGE RANGE:
{page_range}

SCHEMA (STRICT):
{json.dumps(schema_payload, separators=(",", ":"))}

EXTRACTION RULES (NON-NEGOTIABLE):
1. Extract ONLY the fields defined in the schema above.
2. Do NOT invent new fields.
3. Do NOT rename fields.
4. Do NOT output arrays of duplicate fields.
5. Each field must appear EXACTLY ONCE.
6. If a field is missing or unclear, return null.
7. Do NOT infer values from other documents or pages.
8. Use ONLY the provided pages — ignore anything else.

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "<field_name>": "<value or null>"
}}

FORBIDDEN:
- Reclassifying the document
- Returning multiple objects
- Returning nested structures
- Adding confidence, explanations, or metadata
- Markdown or comments

OUTPUT JSON ONLY.
NO TEXT.
NO EXPLANATION.

"""

        user_content = [{"type": "text", "text": "Extract fields."}]
        for img in selected_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img}"}
            })

        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=512,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)

    # ------------------------------------------------------------------
    # Public API (UNCHANGED)
    # ------------------------------------------------------------------
    def assert_extraction_shape(data: Dict[str, Any], schema: Dict[str, Any]):
        expected_fields = {f["name"] for f in schema.get("fields", [])}
        received_fields = set(data.keys())

        if received_fields != expected_fields:
            raise ValueError(
                f"Extraction mismatch. Expected {expected_fields}, got {received_fields}"
            )

    async def analyze_document(
        self,
        file_content: bytes,
        filename: str,
        schemas: List[Dict],
        progress_callback=None,
        check_cancelled_callback=None
    ) -> Dict[str, Any]:

        if progress_callback:
            await progress_callback("Converting to images", 10)

        images = await self._convert_to_images(file_content, filename)

        if progress_callback:
            await progress_callback("Detecting document structure", 30)

        schema_map = {}

        for s in schemas:
            if isinstance(s, dict) and "type_name" in s:
                schema_map[s["type_name"]] = s
 

        pages = await self._classify_pages_batched(
            images,
            [
                {
                    "name": s["type_name"],
                    "description": s.get("description", "")
                }
                for s in schema_map.values()
            ],
            batch_size=5
        )

        structure = self._group_pages_into_documents(pages)


        findings = []

        for idx, doc in enumerate(structure, start=1):
            if check_cancelled_callback and await check_cancelled_callback():
                break

            if progress_callback:
                await progress_callback(
                    f"Extracting {doc['type']} ({idx}/{len(structure)})",
                    30 + int((idx / len(structure)) * 60)
                )

            schema = schema_map.get(doc["type"])

            if not schema or not isinstance(schema, dict):
                raise RuntimeError(
                    f"Invalid schema for document type '{doc['type']}'. "
                    f"Expected dict, got {type(schema)}"
                )


            data = await self._extract_fields(
                doc["type"],
                doc["page_range"],
                images,
                schema
            )

            findings.append({
                "type": doc["type"],
                "page_range": doc["page_range"],
                "data": data,
                "confidence": 1.0
            })

            await asyncio.sleep(2)  # S0 throttle

        if progress_callback:
            await progress_callback("Finalizing analysis", 95)

        return {"findings": findings}

ai_service = AIService()