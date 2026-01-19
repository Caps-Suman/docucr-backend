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
from openai import AsyncAzureOpenAI
from pdf2image import convert_from_bytes
from PIL import Image


class AIService:
    def __init__(self):
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        self.api_version = os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        )

        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            api_version=self.api_version,
            azure_endpoint=self.endpoint
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

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

    async def _detect_structure_chunked(
        self,
        images: List[str],
        document_types: List[str],
        window_size: int = 2
    ) -> List[Dict[str, str]]:

        documents: List[Dict[str, str]] = []
        page_cursor = 1

        for i in range(0, len(images), window_size):
            chunk = images[i:i + window_size]

            system_prompt = f"""
You are identifying logical documents in medical paperwork.

Allowed document types:
{", ".join(document_types)}

CRITICAL RULES:
- Superbills often span multiple pages.
- Page 1 may contain patient/insurance info.
- Following pages may contain CPT/ICD codes.
- If pages share patient, provider, date, or layout,
  they MUST be merged into ONE document.

When uncertain, prefer MERGING over splitting.

Page numbering starts at {page_cursor}.

Output JSON strictly:
{{
  "documents": [
    {{ "type": "<DocumentType>", "page_range": "start-end" }}
  ]
}}
"""

            user_content = [{"type": "text", "text": "Analyze these pages."}]
            for img in chunk:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}
                })

            try:
                response = await self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=256,
                    response_format={"type": "json_object"}
                )

                result = json.loads(response.choices[0].message.content)
                documents.extend(result.get("documents", []))

            except Exception as e:
                if "RateLimitReached" in str(e):
                    await asyncio.sleep(60)
                    continue
                raise

            page_cursor += len(chunk)
            await asyncio.sleep(60)  # Azure S0 safety

        return self._normalize_documents(documents)

    # ------------------------------------------------------------------
    # Normalize & merge overlapping / adjacent documents
    # ------------------------------------------------------------------

    def _normalize_documents(
    self,
    docs: List[Dict[str, str]]
) -> List[Dict[str, str]]:

        def parse(r):
            return tuple(map(int, r.split("-")))

        if not docs:
            return []

        # Sort by start asc, end desc (larger ranges first)
        docs_sorted = sorted(
            docs,
            key=lambda d: (parse(d["page_range"])[0], -parse(d["page_range"])[1])
        )

        final_docs = []

        for doc in docs_sorted:
            start, end = parse(doc["page_range"])

            is_subset = False
            for kept in final_docs:
                ks, ke = parse(kept["page_range"])

                # FULLY contained → discard
                if start >= ks and end <= ke:
                    is_subset = True
                    break

            if not is_subset:
                final_docs.append(doc)

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

        schema_map = {s["type_name"]: s for s in schemas}

        structure = await self._detect_structure_chunked(
            images,
            list(schema_map.keys()),
            window_size=2
        )

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

            await asyncio.sleep(60)  # S0 throttle

        if progress_callback:
            await progress_callback("Finalizing analysis", 95)

        return {"findings": findings}

ai_service = AIService()
