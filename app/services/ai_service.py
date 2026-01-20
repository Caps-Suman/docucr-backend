# import os
# import io
# import json
# import base64
# import asyncio
# from typing import List, Dict, Any, Optional
# from openai import AsyncAzureOpenAI
# from pdf2image import convert_from_bytes
# from PIL import Image

# class AIService:
#     def __init__(self):
#         self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
#         self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#         self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
#         self.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        
#         self.client = None
#         if self.api_key and self.endpoint:
#             self.client = AsyncAzureOpenAI(
#                 api_key=self.api_key,
#                 api_version=self.api_version,
#                 azure_endpoint=self.endpoint
#             )

#     def _encode_image(self, image: Image.Image) -> str:
#         buffered = io.BytesIO()

#         # CRITICAL FIX: normalize image mode
#         if image.mode in ("RGBA", "LA", "P"):
#             image = image.convert("RGB")

#         image.save(buffered, format="JPEG", quality=90)
#         return base64.b64encode(buffered.getvalue()).decode("utf-8")

#     async def analyze_document(self, file_content: bytes, filename: str, schemas: List[Dict], progress_callback=None, check_cancelled_callback=None) -> Dict[str, Any]:
#         """
#         Analyze document using Azure OpenAI against multiple potential schemas.
#         schemas: List of {"type_name": str, "fields": List[Dict]}
#         progress_callback: async function(status: str, progress: int)
#         check_cancelled_callback: async function() -> bool
#         """
#         if not self.client:
#             raise Exception("Azure OpenAI client not initialized. Check environment variables.")

#         if progress_callback:
#             await progress_callback("Converting to images...", 10)

#         # Convert PDF/Image to list of base64 images
#         images = []
#         if filename.lower().endswith('.pdf'):
#             loop = asyncio.get_event_loop()
#             pil_images = await loop.run_in_executor(None, convert_from_bytes, file_content)
#             images = [self._encode_image(img) for img in pil_images]
#         else:
#             image = Image.open(io.BytesIO(file_content))
#             images = [self._encode_image(image)]

#         total_pages = len(images)
#         if progress_callback:
#             await progress_callback(f"Prepared {total_pages} pages for analysis...", 30)

#         # Construct Prompt
#         schemas_desc = json.dumps(schemas, separators=(",", ":"))
#         schemas_desc = schemas_desc[:1500] 
#         system_prompt = f"""You are an advanced document processing AI.
#         Your task is to analyze the provided document images. The document may be a single file containing multiple logical documents (e.g., an Invoice followed by a Receipt).
        
#         Available Document Types and Extraction Rules:
#         {schemas_desc}
        
#         Instructions:
#         1. Scan the entire file.
#         2. Identify ALL occurrences of the provided Document Types.
#         3. For each occurrence, determine the applicable "page_range" (e.g., "1-2", "3").
#         4. Extract data strictly based on the "fields" defined for that Document Type.
#         5. If a document section does NOT match any provided type, INFER the most likely document type name (e.g. "Bank Statement", "Medical Record") based on the content. DO NOT use "Unknown".
        
#         Output Format (JSON strictly):
#         {{
#             "findings": [
#                 {{
#                     "type": "<Document Type Name or Inferred Name>",
#                     "page_range": "start-end",
#                     "data": {{ <extracted_fields> }},
#                     "confidence": <0.0-1.0>
#                 }}
#             ]
#         }}
#         """

#         # Batch Processing Optimization
#         BATCH_SIZE = 2
#         all_findings = []
        
#         # Limit concurrent requests to avoid Rate Limiting (TPM)
#         # sem = asyncio.Semaphore(3)

#         async def process_batch(start_idx: int, batch_images: List[str]):
#                 # Check for cancellation
#                 if check_cancelled_callback and await check_cancelled_callback():
#                     # We can't easily "cancel" other running tasks in gather without complex logic,
#                     # but we can abort this one.
#                     return []

#                 start_page = start_idx + 1
#                 end_page = min(start_idx + len(batch_images), total_pages)
                
#                 # Progress Update (Approximate, as they run in parallel)
#                 if progress_callback:
#                     # Calculate approximate progress
#                     # We use a simplified metric here since exact tracking with concurrency is noisy
#                     await progress_callback(f"Analyzing pages...", 
#                                           int((end_page / total_pages) * 80) + 10)

#                 # Construct Batch Prompt
#                 batch_user_content = [
#                     {"type": "text", "text": f"Analyze these specific pages ({start_page} to {end_page} of {total_pages}) and extract logical documents found strictly within this range."}
#                 ]
                
#                 for img_b64 in batch_images:
#                     batch_user_content.append({
#                         "type": "image_url",
#                         "image_url": {
#                             "url": f"data:image/jpeg;base64,{img_b64}"
#                         }
#                     })

#                 try:
#                     response = await self.client.chat.completions.create(
#                         model=self.deployment_name,
#                         messages=[
#                             {"role": "system", "content": system_prompt},
#                             {"role": "user", "content": batch_user_content}
#                         ],
#                         max_tokens=512,
#                         response_format={"type": "json_object"}
#                     )
                    
#                     result = json.loads(response.choices[0].message.content)
#                     return result.get("findings", [])
                    
#                 # except Exception as e:
#                 #     print(f"Error analyzing batch {start_page}-{end_page}: {e}")
#                 #     # Return error finding
#                 #     return [{
#                 #         "type": "Error",
#                 #         "page_range": f"{start_page}-{end_page}",
#                 #         "data": {"error": f"Batch analysis failed: {str(e)}"},
#                 #         "confidence": 0.0
#                 #     }]
#                 except Exception as e:
#                     if "RateLimitReached" in str(e):
#                         await asyncio.sleep(60)
#                         return await process_batch(start_idx, batch_images)
#                     raise e

#         # Create tasks
#         tasks = []
#         for i in range(0, total_pages, BATCH_SIZE):
#             batch_imgs = images[i : i + BATCH_SIZE]
#             tasks.append(process_batch(i, batch_imgs))

#         # Execute concurrently
#         results = []
#         for task in tasks:
#             result = await task
#             results.append(result)
#             await asyncio.sleep(60)  # hard throttle

        
#         # Flatten results
#         for batch_findings in results:
#             all_findings.extend(batch_findings)

#         if progress_callback:
#             await progress_callback("Finalizing analysis...", 95)

#         return {"findings": all_findings}

# ai_service = AIService()
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
        all_pages = []
        doc_type_block = self._format_document_types(document_types)

        system_prompt = f"""
You are classifying individual medical document pages.

DOCUMENT TYPES (AUTHORITATIVE — USE DESCRIPTIONS):
{doc_type_block}

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
