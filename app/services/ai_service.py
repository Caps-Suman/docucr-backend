
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
        """
        Deterministic document instance builder.
        ZERO AI decisions here.
        """

        documents = []
        current = None
        prev = None

        def normalize(v):
            return v.strip().upper() if isinstance(v, str) else None

        def should_split(prev, curr):
            # 1. Document type change
            if curr["type"] != prev["type"]:
                return True

            s1 = prev.get("signals", {})
            s2 = curr.get("signals", {})

            # 2. Patient identity change (HARD STOP)
            if normalize(s1.get("patient_name")) != normalize(s2.get("patient_name")):
                return True

            if normalize(s1.get("dob")) != normalize(s2.get("dob")):
                return True

            # 3. Claim / invoice boundary
            if s1.get("claim_number") and s2.get("claim_number"):
                if s1["claim_number"] != s2["claim_number"]:
                    return True

            if s1.get("invoice_number") and s2.get("invoice_number"):
                if s1["invoice_number"] != s2["invoice_number"]:
                    return True

            # 4. Date of service change
            if s1.get("date_of_service") and s2.get("date_of_service"):
                if s1["date_of_service"] != s2["date_of_service"]:
                    return True

            # 5. Header restart explicitly detected
            if s2.get("header_restart") is True:
                return True

            # 6. Page numbering sanity
            if curr["page"] != prev["page"] + 1:
                return True

            return False

        for page in pages:
            if not current:
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"]
                }
                prev = page
                continue

            if should_split(prev, page):
                documents.append(current)
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"]
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
    You are classifying ONE page of a medical document.

    DOCUMENT TYPES:
    {document_type_block}

    TASKS (STRICT):
    1. Identify document TYPE using DESCRIPTION.
    2. Extract PATIENT identity and instance signals.

    YOU MUST TRY TO EXTRACT PATIENT INFO.
    If not visible, return null.

    Set header_restart = true IF:
    - CPT / ICD table header repeats
    - Patient info block restarts
    - Provider + patient section repeats
    - Charges table starts again

    SIGNALS TO EXTRACT:
    - patient_name
    - dob
    - member_id
    - page_label
    - header_restart

    OUTPUT JSON ONLY:
    {{
    "page": {page_no},
    "type": "<DocumentTypeName>",
    "signals": {{
        "patient_name": null,
        "dob": null,
        "member_id": null,
        "page_label": null,
        "header_restart": false
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

            page = json.loads(response.choices[0].message.content)
            page["type"] = page["type"].strip().upper()
            return page

        pages = []

        for i in range(0, total_pages, batch_size):
            batch = [
                process_page(images[j], j + 1)
                for j in range(i, min(i + batch_size, total_pages))
            ]

            results = await asyncio.gather(*batch)
            pages.extend(results)
            await asyncio.sleep(3)

        return pages


    # ------------------------------------------------------------------
    # Public API (UNCHANGED)
    # ------------------------------------------------------------------

    async def analyze_document(
        self,
        file_content: bytes,
        filename: str,
        schemas: List[Dict],
        db:Session,
        document_id: int,   # ← REQUIRED
        progress_callback=None,
        check_cancelled_callback=None
    ) -> Dict[str, Any]:

        if progress_callback:
            await progress_callback("Converting to images", 10)

        images = await self._convert_to_images(file_content, filename)

        if progress_callback:
            await progress_callback("Detecting document structure", 30)

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

        pages = await self._detect_structure_chunked(
            images,
            document_types
        )

        structure = self.build_document_instances(pages)
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
            if not schema:
    # ALWAYS persist unverified documents
                unverified_doc = UnverifiedDocument(
                    document_id=document_id,
                    suspected_type=doc["type"],
                    page_range=doc["page_range"],
                    extracted_data={},
                    status="PENDING"
                )
                db.add(unverified_doc)
                continue

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

            await asyncio.sleep(5)  # S0 throttle

        if progress_callback:
            await progress_callback("Finalizing analysis", 95)
        derived_documents = Counter()

        # from verified docs
        for f in findings:
            if f.get("type"):
                derived_documents[f["type"]] += 1

        # from unverified docs (DB)
        unverified = db.query(UnverifiedDocument).filter(
            UnverifiedDocument.document_id == document_id
        ).all()

        for u in unverified:
            if u.suspected_type:
                derived_documents[u.suspected_type] += 1

        db.commit()
        return {
            "derived_documents": dict(derived_documents),
            "findings": findings}

ai_service = AIService()