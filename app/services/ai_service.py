
#self.client = AsyncOpenAI(
        #     api_key=os.getenv("OPENAI_API_KEY")
        # )
from collections import Counter
import os
import io
import json
import base64
import asyncio
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from openai import AsyncAzureOpenAI, AsyncOpenAI
from pdf2image import convert_from_bytes
from PIL import Image

from app.models import document
from app.models.unverified_document import UnverifiedDocument


class AIService:
    def __init__(self):
        # self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        # self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        # self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        # self.api_version = os.getenv(
        #     "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        # )

        # self.client = AsyncAzureOpenAI(
        #     api_key=self.api_key,
        #     api_version=self.api_version,
        #     azure_endpoint=self.endpoint
        # )
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def format_document_types(self, document_types: List[Dict[str, str]]) -> str:
        """
        document_types MUST be a list of:
        { "name": str, "description": str }
        """
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
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    
    async def _convert_to_images(self, file_content: bytes, filename: str) -> List[str]:
        if filename.lower().endswith(".pdf"):
            loop = asyncio.get_event_loop()
            pages = await loop.run_in_executor(None, convert_from_bytes, file_content)
            return [self._encode_image(p) for p in pages]

        image = Image.open(io.BytesIO(file_content))
        return [self._encode_image(image)]
    
    def build_document_instances(self, pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        documents = []
        current = None
        prev = None

        def should_split(prev, curr):
            if curr["type"] != prev["type"]:
                return True

            s2 = curr.get("signals", {})

            if s2.get("header_restart") is True:
                return True

            # default: CONTINUE
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
            {
                "type": d["type"],
                "page_range": f"{d['start']}-{d['end']}"
            }
            for d in documents
        ]





    # ------------------------------------------------------------------
    # Phase 1 — Structure detection (chunked + domain aware)
    # ------------------------------------------------------------------

#     async def _detect_structure_chunked(
#     self,
#     images: List[str],
#     document_types: List[Dict[str, str]],
#     window_size: int = 2,
#     batch_size: int = 3,
# ) -> List[Dict[str, str]]:

#         document_type_block = self.format_document_types(document_types)
#         total_pages = len(images)

#         async def process_chunk(
#             chunk_images: List[str],
#             start_page: int
#         ) -> List[Dict[str, str]]:

#             system_prompt = f"""
#     You are identifying logical documents in medical paperwork.

#     DOCUMENT TYPES (AUTHORITATIVE — USE BOTH NAME AND DESCRIPTION):
#     {document_type_block}

#     IMPORTANT:
#     Each document type has a NAME and a DESCRIPTION.
#     You MUST use the DESCRIPTION as the PRIMARY source of truth.
#     The NAME alone is NOT sufficient to classify a document.

#     --------------------------------------------------
#     CLASSIFICATION PRINCIPLES (STRICT)
#     --------------------------------------------------

#     1. DOCUMENT MERGING (CRITICAL)
#     - A single logical document may span multiple pages.
#     - Page 1 may contain patient / insurance / demographics.
#     - Following pages may contain CPT, ICD, procedures, or charges.
#     - If pages share ANY of the following, they MUST be merged:
#     • Patient identity
#     • Provider identity
#     • Date of service
#     • Layout / formatting / headers / footers
#     • Continuation indicators (e.g., repeated table headers)
#     -merge ONLY when page ranges overlap,
#     NOT when they are merely adjacent

#     When uncertain, ALWAYS prefer MERGING over splitting.

#     --------------------------------------------------
#     DOCUMENT TYPE DECISION RULES (DESCRIPTION-DRIVEN)
#     --------------------------------------------------

#     - Use the DESCRIPTION to decide the document type.
#     - Match what the document IS, not what keywords appear.
#     - Ignore superficial overlap.

#     General guidance (DO NOT override descriptions):
#     - CPT / ICD / procedures → Superbill
#     - Totals / balances / billing → Invoice
#     - Patient identity only → Demographics
#     If a page clearly starts a NEW instance of the SAME document type
#     (e.g., header restarts, page labeled Page 1, new claim, new DOS),
#     you MUST start a new document even if the type is the same.

#     NEVER invent a document type.
#     NEVER output "Unknown".

#     --------------------------------------------------
#     OUTPUT RULES (NON-NEGOTIABLE)
#     --------------------------------------------------

#     - EACH page MUST belong to EXACTLY ONE document
#     - EACH document MUST have EXACTLY ONE type

#     Page numbering starts at {start_page}.

#     --------------------------------------------------
#     OUTPUT FORMAT (STRICT JSON ONLY)
#     --------------------------------------------------

#     {{
#     "documents": [
#         {{ "type": "<DocumentTypeName>", "page_range": "start-end", "instance_reason": "NEW_HEADER" }}
#     ]
#     }}

#     JSON ONLY.
#     """

#             user_content = [{"type": "text", "text": "Analyze these pages."}]
#             for img in chunk_images:
#                 user_content.append({
#                     "type": "image_url",
#                     "image_url": {"url": f"data:image/jpeg;base64,{img}"}
#                 })

#             response = await self.client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_content}
#                 ],
#                 max_tokens=1024,
#                 response_format={"type": "json_object"}
#             )

#             payload = json.loads(response.choices[0].message.content)

#             normalized = []
#             for doc in payload.get("documents", []):
#                 if isinstance(doc.get("type"), str):
#                     doc["type"] = doc["type"].strip().upper()
#                 normalized.append(doc)

#             return normalized

#         # ------------------------------
#         # Build chunk tasks
#         # ------------------------------
#         tasks = []
#         documents: List[Dict[str, str]] = []

#         page_cursor = 1
#         chunk_specs = []

#         for i in range(0, total_pages, window_size):
#             chunk_specs.append((
#                 images[i:i + window_size],
#                 page_cursor
#             ))
#             page_cursor += len(images[i:i + window_size])

#         # ------------------------------
#         # Execute in batches
#         # ------------------------------
#         for i in range(0, len(chunk_specs), batch_size):
#             batch = chunk_specs[i:i + batch_size]

#             batch_tasks = [
#                 process_chunk(chunk, start_page)
#                 for chunk, start_page in batch
#             ]

#             results = await asyncio.gather(*batch_tasks, return_exceptions=True)

#             for r in results:
#                 if isinstance(r, Exception):
#                     raise r
#                 documents.extend(r)

#             # light throttle for safety
#             await asyncio.sleep(5)

#         return self._normalize_documents(documents)


#     # ------------------------------------------------------------------
#     # Normalize & merge overlapping / adjacent documents
#     # ------------------------------------------------------------------

#     def _normalize_documents(
#     self,
#     docs: List[Dict[str, str]]
# ) -> List[Dict[str, str]]:

#         def parse(r):
#             return tuple(map(int, r.split("-")))

#         if not docs:
#             return []

#         # Sort by start asc, end desc (larger ranges first)
#         docs_sorted = sorted(
#             docs,
#             key=lambda d: (parse(d["page_range"])[0], -parse(d["page_range"])[1])
#         )

#         final_docs = []

#         for doc in docs_sorted:
#             start, end = parse(doc["page_range"])

#             is_subset = False
#             for kept in final_docs:
#                 ks, ke = parse(kept["page_range"])

#                 # FULLY contained → discard
#                 if start >= ks and end <= ke:
#                     is_subset = True
#                     break

#             if not is_subset:
#                 final_docs.append(doc)

#         return final_docs


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

        system_prompt = f"""
Extract data for document type: {doc_type}

Schema:
{json.dumps(schema, separators=(",", ":"))}

Rules:
- Extract ONLY defined fields
- Missing fields → null
- Output JSON only
"""

        user_content = [{"type": "text", "text": "Extract fields."}]
        for img in selected_images:
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

        return json.loads(response.choices[0].message.content)
    async def _detect_structure_chunked(
    self,
    images: List[str],
    document_types: List[Dict[str, str]],
    window_size: int = 1,   # 🔴 PER PAGE ONLY
    batch_size: int = 4,
) -> List[Dict[str, Any]]:

        document_type_block = self.format_document_types(document_types)
        total_pages = len(images)

        async def process_page(img: str, page_no: int):

            system_prompt = f"""
    You are classifying pages of medical documents.

DOCUMENT TYPES:
{document_type_block}

Your job is NOT to create documents.
Your job is ONLY to analyze ONE page and emit signals.

STRICT RULES:

1. Identify document type USING DESCRIPTION, not keywords.
2. Detect whether this page STARTS a new document or CONTINUES the previous one.

CONTINUATION RULES (CRITICAL):
- If a page contains diagnosis tables, ICD codes, CPT codes, or procedure lists
  AND does NOT contain patient name, DOB, or insurance header,
  THEN this page is a CONTINUATION of the previous page’s document.
- Such pages MUST NOT start a new document.

HEADER RESTART = true ONLY if:
- Patient name or DOB is visible
- OR the page explicitly says "Page 1"
- OR a new patient/provider block starts

CRITICAL CONTINUATION RULE:
If this page visually continues tables, line items, or billing rows
from the previous page (same columns, same layout),
then:
  - continues_previous = true
  - header_restart = false
Even if patient name or DOB is not visible.
OUTPUT JSON ONLY:

{{
  "type": "<DocumentTypeName>",
  "signals": {{
    "has_patient_header": boolean,
    "continues_previous": boolean,
    "header_restart": boolean,
    "patient_name": null or string,
    "dob": null or string
  }}
}}  
"""
            user_content = [
                {"type": "text", "text": "Analyze this page."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}
                }
            ]

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=512,
                response_format={"type": "json_object"}
            )

            raw = json.loads(response.choices[0].message.content)

            return {
                "page": page_no,                      # 🔒 YOU control this
                "type": raw.get("type", "UNKNOWN").strip().upper(),
                "signals": raw.get("signals", {})
            }


        pages = []

        for i in range(0, total_pages, batch_size):
            batch = [
                process_page(images[j], j + 1)
                for j in range(i, min(i + batch_size, total_pages))
            ]

            results = await asyncio.gather(*batch)
            pages.extend(results)
            await asyncio.sleep(1.5)

        return pages


    # ------------------------------------------------------------------
    # Public API (UNCHANGED)
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
        # 4. PAGE NORMALIZATION (YOU OWN PAGE NUMBERS)
        # --------------------------------------------------
        normalized_pages = {}
        for p in pages:
            page_no = p["page"]
            normalized_pages[page_no] = {
                "page": page_no,
                "type": p["type"],
                "signals": p.get("signals", {})
            }

        if len(normalized_pages) != total_pages:
            raise RuntimeError(
                f"Page mismatch: expected {total_pages}, "
                f"got {len(normalized_pages)}. "
                f"Pages: {sorted(normalized_pages.keys())}"
            )

        ordered_pages = [
            normalized_pages[i]
            for i in range(1, total_pages + 1)
        ]

        # --------------------------------------------------
        # 5. GROUP INTO DOCUMENT INSTANCES (DETERMINISTIC)
        # --------------------------------------------------
        structure = self.build_document_instances(ordered_pages)

        findings: List[Dict[str, Any]] = []
        # --------------------------------------------------
        # 6. EXTRACTION + PERSISTENCE (ONE ROW PER INSTANCE)
        # --------------------------------------------------
        for idx, doc in enumerate(structure, start=1):

            if check_cancelled_callback and await check_cancelled_callback():
                break

            if progress_callback:
                await progress_callback(
                    f"Extracting {doc['type']} ({idx}/{len(structure)})",
                    30 + int((idx / len(structure)) * 60)
                )

            doc_type = doc["type"]
            page_range = doc["page_range"]
            schema = schema_map.get(doc_type)

            # ---------- UNVERIFIED ----------
            if not schema:
                db.add(UnverifiedDocument(
                    document_id=document_id,
                    suspected_type=doc_type,
                    page_range=page_range,
                    extracted_data={},
                    status="PENDING"
                ))
                continue

            # ---------- VERIFIED ----------
            data = await self._extract_fields(
                doc_type,
                page_range,
                images,
                schema
            )

            findings.append({
                "type": doc_type,
                "page_range": page_range,
                "data": data,
                "confidence": 1.0
            })

            await asyncio.sleep(1.5)  # controlled throttle

        # --------------------------------------------------
        # 7. FINALIZE
        # --------------------------------------------------
        derived_documents = Counter()
        
        rows = db.query(UnverifiedDocument).filter(
            UnverifiedDocument.document_id == document_id
        ).all()
        for r in rows:
            derived_documents[r.suspected_type] += 1
        # derived_documents = Counter()

        # for doc in structure:
        #     derived_documents[doc["type"]] += 1

        db.commit()

        if progress_callback:
            await progress_callback("Finalizing analysis", 95)

        return {
            "derived_documents": dict(derived_documents),
            "findings": findings
        }


ai_service = AIService()