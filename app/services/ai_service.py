from collections import Counter
import os
import io
import json
import base64
import asyncio
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from openai import AsyncOpenAI
from pdf2image import convert_from_bytes
from PIL import Image

from app.models import document
from app.models.unverified_document import UnverifiedDocument


class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def format_document_types(self, document_types: List[Dict[str, str]]) -> str:
        lines = []
        for dt in document_types:
            name = dt.get("name", "").strip().upper()
            desc = dt.get("description", "No description provided")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
        # ✅ Higher quality for better OCR accuracy
        image.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def _convert_to_images(self, file_content: bytes, filename: str) -> List[str]:
        if filename.lower().endswith(".pdf"):
            loop = asyncio.get_event_loop()
            # ✅ 200 DPI: sharp enough for vision, small enough to stay fast
            pages = await loop.run_in_executor(
                None,
                lambda: convert_from_bytes(file_content, dpi=200)
            )
            return [self._encode_image(p) for p in pages]

        image = Image.open(io.BytesIO(file_content))
        return [self._encode_image(image)]

    def _safe_parse_json(self, raw: str) -> dict:
        """
        3-tier JSON parse with json_repair fallback.
        Handles truncation, trailing commas, missing braces.
        """
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        # Tier 1: clean parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Tier 2: json_repair
        try:
            from json_repair import repair_json
            return json.loads(repair_json(raw))
        except Exception:
            pass

        # Tier 3: truncate to last closing brace
        last = raw.rfind("}")
        if last != -1:
            try:
                return json.loads(raw[:last + 1])
            except Exception:
                pass

        raise ValueError(f"Could not parse AI response as JSON:\n{raw[:400]}")

    def build_document_instances(self, pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        documents = []
        current = None
        prev = None

        def should_split(prev, curr):
            if curr["type"] != prev["type"]:
                return True
            if curr.get("signals", {}).get("header_restart") is True:
                return True
            return False

        for page in pages:
            if not current:
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"],
                }
                prev = page
                continue

            if should_split(prev, page):
                documents.append(current)
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"],
                }
            else:
                current["end"] = page["page"]

            prev = page

        if current:
            documents.append(current)

        return [
            {"type": d["type"], "page_range": f"{d['start']}-{d['end']}"}
            for d in documents
        ]

    # ------------------------------------------------------------------
    # Phase 1 — Structure detection (per-page, batched)
    # ------------------------------------------------------------------

    async def _detect_structure_chunked(
        self,
        images: List[str],
        document_types: List[Dict[str, str]],
        window_size: int = 1,
        batch_size: int = 6,        # ✅ increased from 4 → process more pages in parallel
    ) -> List[Dict[str, Any]]:

        document_type_block = self.format_document_types(document_types)
        total_pages = len(images)

        async def process_page(img: str, page_no: int):

            system_prompt = f"""You are classifying pages of medical documents.

DOCUMENT TYPES:
{document_type_block}

Your job is ONLY to analyze ONE page and emit signals.

STRICT RULES:
1. Identify document type USING DESCRIPTION, not keywords alone.
2. Detect whether this page STARTS a new document or CONTINUES the previous one.

CONTINUATION RULES (CRITICAL):
- If a page contains diagnosis tables, ICD codes, CPT codes, or procedure lists
  AND does NOT contain patient name, DOB, or insurance header → CONTINUATION.

HEADER RESTART = true ONLY if:
- Patient name or DOB is visible
- OR the page explicitly says "Page 1"
- OR a new patient/provider block starts

OUTPUT EXACTLY THIS JSON (no markdown, no extra keys):
{{
  "type": "<DocumentTypeName>",
  "signals": {{
    "has_patient_header": true,
    "continues_previous": false,
    "header_restart": false,
    "patient_name": null,
    "dob": null
  }}
}}"""

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Classify this page."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img}",
                                    "detail": "high"   # ✅ high-detail for dense medical docs
                                }
                            }
                        ]
                    }
                ],
                max_tokens=256,                        # ✅ classification only needs small output
                response_format={"type": "json_object"}
            )

            raw = self._safe_parse_json(response.choices[0].message.content)

            return {
                "page": page_no,
                "type": raw.get("type", "UNKNOWN").strip().upper(),
                "signals": raw.get("signals", {})
            }

        pages = []

        for i in range(0, total_pages, batch_size):
            batch_tasks = [
                process_page(images[j], j + 1)
                for j in range(i, min(i + batch_size, total_pages))
            ]
            results = await asyncio.gather(*batch_tasks)
            pages.extend(results)
            # ✅ Reduced sleep: only throttle between batches, not every page
            if i + batch_size < total_pages:
                await asyncio.sleep(0.5)

        return pages

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

        start, end = map(int, page_range.split("-"))
        selected_images = images[start - 1:end]

        # ✅ Build explicit field list so model knows exactly what to look for
        fields_list = schema.get("fields", [])
        field_names = [f["fieldName"] for f in fields_list if "fieldName" in f]
        field_block = "\n".join(f"- {fn}" for fn in field_names)

        system_prompt = f"""You are extracting structured data from a medical document of type: {doc_type}

FIELDS TO EXTRACT (extract ALL of these, use null if not found):
{field_block}

FULL SCHEMA:
{json.dumps(schema, separators=(",", ":"))}

RULES:
- Extract ONLY the fields listed above
- If a field is not visible on the page → null
- Preserve exact values (dates, codes, amounts) as they appear
- Output JSON only — no markdown, no explanation

OUTPUT FORMAT:
{{
  "fields": {{
    "fieldName1": "value or null",
    "fieldName2": "value or null"
  }}
}}"""

        user_content: List[Dict] = [{"type": "text", "text": "Extract all fields from these pages."}]
        for img in selected_images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img}",
                    "detail": "high"   # ✅ high-detail for extraction accuracy
                }
            })

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=2048,           # ✅ was 512 — enough for full field extraction
            response_format={"type": "json_object"}
        )

        return self._safe_parse_json(response.choices[0].message.content)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_document(
        self,
        file_content: bytes,
        filename: str,
        schemas: List[Dict],
        db: Session,
        document_id: int,
        progress_callback=None,
        check_cancelled_callback=None
    ) -> Dict[str, Any]:

        # --------------------------------------------------
        # 0. HARD RESET (IDEMPOTENCY GUARANTEE)
        # --------------------------------------------------
        db.query(UnverifiedDocument).filter(
            UnverifiedDocument.document_id == document_id
        ).delete()
        db.commit()

        # --------------------------------------------------
        # 1. IMAGE CONVERSION
        # --------------------------------------------------
        if progress_callback:
            await progress_callback("Converting to images", 10)

        images = await self._convert_to_images(file_content, filename)
        total_pages = len(images)

        # --------------------------------------------------
        # 2. SCHEMA PREP
        # --------------------------------------------------
        schema_map = {
            s["type_name"].strip().upper(): s
            for s in schemas
            if "type_name" in s
        }

        document_types = [
            {
                "name": s["type_name"].strip().upper(),
                "description": s.get("description", "")
            }
            for s in schemas
        ]

        # --------------------------------------------------
        # 3. PAGE CLASSIFICATION (AI)
        # --------------------------------------------------
        if progress_callback:
            await progress_callback("Detecting document structure", 30)

        pages = await self._detect_structure_chunked(images, document_types)

        # --------------------------------------------------
        # 4. PAGE NORMALIZATION
        # --------------------------------------------------
        normalized_pages = {p["page"]: p for p in pages}

        if len(normalized_pages) != total_pages:
            raise RuntimeError(
                f"Page mismatch: expected {total_pages}, "
                f"got {len(normalized_pages)}. "
                f"Pages: {sorted(normalized_pages.keys())}"
            )

        ordered_pages = [normalized_pages[i] for i in range(1, total_pages + 1)]

        # --------------------------------------------------
        # 5. GROUP INTO DOCUMENT INSTANCES
        # --------------------------------------------------
        structure = self.build_document_instances(ordered_pages)

        # --------------------------------------------------
        # 6. EXTRACTION — run verified docs concurrently per batch
        # --------------------------------------------------
        findings: List[Dict[str, Any]] = []
        extraction_batch_size = 3   # ✅ run up to 3 extractions in parallel

        verified_docs = [(idx, doc) for idx, doc in enumerate(structure, 1) if schema_map.get(doc["type"])]
        unverified_docs = [(idx, doc) for idx, doc in enumerate(structure, 1) if not schema_map.get(doc["type"])]

        # Save unverified immediately
        for _, doc in unverified_docs:
            db.add(UnverifiedDocument(
                document_id=document_id,
                suspected_type=doc["type"],
                page_range=doc["page_range"],
                extracted_data={},
                status="PENDING"
            ))
        db.commit()

        # ✅ Extract verified docs in parallel batches
        for i in range(0, len(verified_docs), extraction_batch_size):
            batch = verified_docs[i:i + extraction_batch_size]

            if check_cancelled_callback and await check_cancelled_callback():
                break

            if progress_callback:
                first_idx = batch[0][0]
                await progress_callback(
                    f"Extracting {batch[0][1]['type']} ({first_idx}/{len(structure)})",
                    30 + int((first_idx / len(structure)) * 60)
                )

            async def extract_one(idx_doc):
                idx, doc = idx_doc
                data = await self._extract_fields(
                    doc["type"],
                    doc["page_range"],
                    images,
                    schema_map[doc["type"]]
                )
                return {
                    "type": doc["type"],
                    "page_range": doc["page_range"],
                    "data": data,
                    "confidence": 1.0
                }

            batch_results = await asyncio.gather(
                *[extract_one(item) for item in batch],
                return_exceptions=True
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"[extraction] batch item failed: {result}")
                else:
                    findings.append(result)

            # ✅ Short throttle between extraction batches only
            if i + extraction_batch_size < len(verified_docs):
                await asyncio.sleep(0.5)

        # --------------------------------------------------
        # 7. FINALIZE
        # --------------------------------------------------
        derived_documents = Counter()
        rows = db.query(UnverifiedDocument).filter(
            UnverifiedDocument.document_id == document_id
        ).all()
        for r in rows:
            derived_documents[r.suspected_type] += 1

        db.commit()

        if progress_callback:
            await progress_callback("Finalizing analysis", 95)

        return {
            "derived_documents": dict(derived_documents),
            "findings": findings
        }


ai_service = AIService()