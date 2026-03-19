# docucr Backend

A production-ready, PaaS-deployable backend for the **docucr** document processing platform. Built with FastAPI (Python 3.11), it powers intelligent document management, AI-driven extraction, multi-tenant access control, and real-time communication.

---

## Table of Contents

1. [Key Features](#key-features)
2. [Module Functionality Guide](#module-functionality-guide)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Database Models](#database-models)
6. [API Endpoints](#api-endpoints)
7. [Authentication & Authorization Flow](#authentication--authorization-flow)
8. [RBAC — Roles, Modules & Privileges](#rbac--roles-modules--privileges)
9. [Services](#services)
10. [Environment Variables](#environment-variables)
11. [Local Development Setup](#local-development-setup)
12. [Database Migrations](#database-migrations)
13. [Seeding Initial Data](#seeding-initial-data)
14. [Running the Server](#running-the-server)
15. [Testing](#testing)
16. [Docker Deployment](#docker-deployment)
17. [API Documentation](#api-documentation)
18. [Security](#security)

---

## Key Features

### Core & Identity Access Management
- Full JWT-based authentication with Two-Factor Authentication (OTP via email)
- Role-Based Access Control (RBAC) with module-level and submodule-level privilege granularity
- Multi-tenant architecture — every resource is scoped to an `Organisation`
- User management with profile images, supervisor hierarchy, and client mappings
- Superadmin support with temporary session tokens for org management

### Document Management
- Secure multi-file upload and storage via AWS S3
- Document type classification and extraction template system
- Internal document sharing between users within an organization
- External document sharing via password-protected, expiring token links
- Document archiving, status tracking (upload progress, error messages)
- AI-powered document classification and field extraction (GPT-4o via Azure OpenAI)
- Unverified document detection with suspected type and pending review workflow

### Forms & Dynamic Data
- Dynamic form schema builder supporting: text, textarea, number, email, select, checkbox, radio, date
- Form field validation rules and default values stored as JSON
- Form data linked to documents via `DocumentFormData`

### Standard Operating Procedures (SOPs)
- SOP management with provider, client, and workflow linkage
- SOP document upload and AI-driven extraction of billing/coding guidelines
- Provider-client-SOP mapping

### System & Workflow
- Webhook integration for event-based external notifications
- Full activity audit logging (action, entity type, entity ID, IP, user agent)
- Real-time WebSocket support for live dashboard updates and notifications
- Network printer management (RAW, IPP, LPD protocols) with mDNS discovery
- NPI registry lookup for healthcare provider verification
- Dashboard statistics for both admin and end-user views

---

## System Architecture

```mermaid
graph TD
    FE["Frontend\nReact SPA · port 4200"]
    BE["Backend\nFastAPI · port 8000"]
    DB[("PostgreSQL\nSchema: docucr")]
    S3["AWS S3\nDocument Storage"]
    AI["Azure OpenAI\nGPT-4o"]
    EMAIL["SMTP Server\n2FA OTPs & Notifications"]
    WH["External Systems\nWebhooks"]
    PR["Network Printers\nRAW / IPP / LPD"]
    EXT["External Users\nPublic Share links"]

    FE -- "HTTPS + JWT Bearer" --> BE
    BE -- "SQLAlchemy ORM" --> DB
    BE -- "boto3 SDK" --> S3
    BE -- "openai SDK" --> AI
    BE -- "SMTP" --> EMAIL
    BE -- "HTTP POST · HMAC-signed payload" --> WH
    BE -- "Socket / IPP / LPD" --> PR
    EXT -- "token URL → /public/share/:token" --> FE
```

---

## Module Functionality Guide

This section explains what each module does, how it works, and what business problem it solves. Use this as a plain-language guide to understand the system before diving into the technical details.

---

### Module 1 — Authentication & Identity Access Management

**What it does:**
This module handles everything related to who can log in, how their identity is verified, and what they are allowed to do. It is the security backbone of the entire platform.

**How it works — step by step:**

1. **Login:** A user submits their email and password. The system verifies the password using bcrypt hashing. If the credentials are correct and the user's account is active, a 6-digit OTP is sent to their registered email address.

2. **Two-Factor Authentication (2FA):** The user enters the OTP from their email. The OTP is single-use and expires within 5 minutes. This extra step ensures that even if a password is compromised, the account stays protected.

3. **Role Selection:** If the user belongs to multiple roles or organisations, they are prompted to select which role/org they want to work under for this session. Each role gives access to different parts of the system.

4. **Token Issuance:** After successful authentication, two tokens are issued:
   - An **access token** (valid for 60 minutes) — used on every API request.
   - A **refresh token** (valid for 24 hours) — used to silently get a new access token without re-logging in.

5. **Password Reset:** Users can request a password reset OTP via email, then submit the OTP with a new password to regain access.

6. **Superadmin Flow:** A superadmin account is not tied to a specific organisation. On login, they receive a temporary token that only allows them to select an organisation to manage. Once an org is selected, they get a full session token scoped to that org.

**Who uses it:** Every user of the platform — from regular document processors to organisation administrators and system superadmins.

**Authentication Flow Diagram:**

```mermaid
flowchart TD
    A([User]) --> B["POST /api/auth/login\nemail + password"]
    B --> C{Valid credentials?}
    C -->|No| D["401 Unauthorized"]
    C -->|Yes| E{Is Superadmin?}
    E -->|Yes| F["Issue temp token\nsuperadmin: true · temp: true"]
    F --> G["POST /api/organisations/\nselect-organisation/:org_id"]
    G --> H["Issue full access + refresh tokens"]
    E -->|No| I["Send 6-digit OTP to email\nexpiry: 5 min · purpose: LOGIN"]
    I --> J["POST /api/auth/verify-2fa\nemail + otp"]
    J --> K{OTP valid & not expired?}
    K -->|No| L["400 Invalid or Expired OTP"]
    K -->|Yes| M{Multiple roles?}
    M -->|No| H
    M -->|Yes| N["POST /api/auth/select-role\nrole_id + organisation_id"]
    N --> H
    H --> O(["Session active\naccess_token · 60 min\nrefresh_token · 24 hr"])
```

---

### Module 2 — User Management

**What it does:**
This module provides complete control over user accounts. Administrators can create users, assign them roles, map them to clients, activate or deactivate them, and reset their passwords.

**Key functionality:**

- **Create Users:** When an admin creates a new user, they set the user's name, email, role, and organisation. A hashed password is stored securely — users can change it on first login.
- **Role Assignment:** Every user is assigned one or more roles within an organisation. Their role determines what parts of the system they can access and what actions they can perform.
- **Client Mapping:** In a healthcare context, users can be assigned to specific clients (e.g., a billing specialist assigned to handle documents for a particular clinic). This scopes what data they see.
- **Supervisor Hierarchy:** A user can be marked as a supervisor and mapped to supervised users. This supports team-level workflows where senior staff oversee junior staff's work.
- **Activate / Deactivate:** Accounts can be deactivated without deletion. Deactivated users cannot log in but their data and history is preserved.
- **Profile Images:** Users can upload a profile image which is stored in AWS S3 and referenced via URL.
- **Password Management:** Admins can force-change a user's password. Users can also change their own password through the profile module.

**Who uses it:** Organisation administrators and superadmins managing their teams.

---

### Module 3 — Document Management

**What it does:**
This is the core module of the platform. It manages the full lifecycle of documents — from the moment they are uploaded to when they are extracted, shared, reviewed, and archived.

**Key functionality:**

- **Upload:** Users upload one or more files (PDF, images, etc.) via a multipart HTTP request. Each file is streamed to AWS S3. Upload progress is tracked as a percentage and stored in the database so the UI can display a progress bar.
- **Document Metadata:** Each document is tagged with a document type, an extraction template, and optionally a client. This metadata tells the AI module what kind of document it is and what fields to extract.
- **Status Tracking:** Documents move through statuses (e.g., PENDING → PROCESSING → COMPLETED → ERROR). This allows users and administrators to see exactly where each document is in the pipeline.
- **AI Extraction:** Once uploaded, the AI module is optionally triggered (controlled by the `enable_ai` flag) to classify the document and extract structured field data from it.
- **Extracted Data:** Extracted fields are stored in the `ExtractedDocument` table as JSON, along with a confidence score. The frontend can display these fields alongside the document for review.
- **Unverified Documents:** If the AI detects document sections that could not be confidently classified, they are stored as `UnverifiedDocument` records with a `PENDING` status, waiting for a human to verify or reject them.
- **Internal Sharing:** A document can be shared with other users within the same organisation via the `DocumentShare` table. Shared users can view the document but sharing permissions are controlled by the owner.
- **External Sharing:** A password-protected, expiry-linked public URL can be generated for any document. The recipient accesses the document via a token in the URL and must enter a password. This is useful for sharing with external parties who do not have platform accounts.
- **Archiving:** Documents can be archived (soft-removed from the main view) without being permanently deleted, keeping the workspace clean while preserving records.
- **Download:** Users can download the original file from S3 at any time.

**Who uses it:** All platform users — document processors upload and review documents; managers track status and share with external parties; auditors view extracted data.

**Document Lifecycle Diagram:**

```mermaid
flowchart LR
    A["Client uploads file\nmultipart/form-data"] --> B["POST /api/documents/upload"]
    B --> C["Stream to AWS S3\ns3_key stored in DB"]
    C --> D["Status: PENDING"]
    D --> E{enable_ai = true?}
    E -->|Yes| F["Status: PROCESSING\nAI pipeline triggered"]
    F --> G["pdf2image · pdfminer\npytesseract OCR"]
    G --> H["GPT-4o extraction\nusing Template fields"]
    H --> I{Result}
    I -->|Confident fields| J["Status: COMPLETED\nSaved to ExtractedDocument\nwith confidence score"]
    I -->|Unclassified sections| K["Saved to UnverifiedDocument\nstatus: PENDING review"]
    I -->|Failure| L["Status: ERROR\nerror_message stored"]
    E -->|No| J
    J --> M{User action}
    M -->|Archive| N["is_archived = true"]
    M -->|Internal Share| O["DocumentShare record\ncreated per user"]
    M -->|External Share| P["ExternalShare token\nbcrypt password · expiry set"]
    M -->|Download| Q["Stream from S3"]
    M -->|Delete| R["Removed from DB + S3"]
```

---

### Module 4 — Document AI (Classification & Extraction)

**What it does:**
This module powers the intelligent brain of the platform. It uses GPT-4o (via Azure OpenAI) to automatically read, classify, and extract structured data from uploaded documents.

**How it works:**

1. A document is uploaded to S3.
2. The AI module is triggered (either automatically on upload or manually via the `/classify-and-extract` endpoint).
3. The document is downloaded from S3, converted to images (for PDFs, using `pdf2image`), and the text is extracted using `pdfminer.six` and `pytesseract` (OCR for scanned documents).
4. The extracted text, along with the extraction template's field definitions, is sent to GPT-4o as a structured prompt.
5. GPT-4o returns a JSON object with all the detected field values.
6. A JSON repair step handles any malformed outputs from the AI.
7. The results are stored in `ExtractedDocument` with a confidence score. Any unclassifiable sections go into `UnverifiedDocument`.

**Why it matters:** This module eliminates manual data entry. Instead of a user reading a document and typing out patient names, dates, billing codes, etc., the AI reads the document and fills in all the fields automatically.

**Who uses it:** The service is invoked automatically during document upload. Users and admins can also manually trigger re-extraction via the API.

**AI Extraction Pipeline Diagram:**

```mermaid
flowchart TD
    A["Document uploaded to S3"] --> B["AISOPService / DocumentService triggered"]
    B --> C{File type?}
    C -->|PDF| D["pdf2image\nconvert pages to images"]
    C -->|DOCX| E["python-docx\nextract paragraphs"]
    D --> F["pdfminer.six\ntext layer extraction"]
    F --> G{Text available?}
    G -->|No - scanned| H["pytesseract OCR\nimage-to-text"]
    G -->|Yes| I["Raw text ready"]
    H --> I
    E --> I
    I --> J["Build GPT-4o prompt\ntext + Template extraction_fields"]
    J --> K["Azure OpenAI API call\nmodel: gpt-4o"]
    K --> L{Response valid JSON?}
    L -->|Yes| M["Parse field values\nstore in ExtractedDocument\nconfidence score saved"]
    L -->|No - malformed| N["JSON repair step\nauto-fix common issues"]
    N --> O{Repaired?}
    O -->|Yes| M
    O -->|No| P["Unclassified sections\nsaved to UnverifiedDocument\nstatus: PENDING"]
```

---

### Module 5 — Document Types & Extraction Templates

**What it does:**
This module allows administrators to define the "vocabulary" the AI uses when processing documents. Without this configuration, the AI would not know what fields to look for in each document type.

**Document Types:**
A document type is a category of document (e.g., "Insurance Card", "Medical Record", "Referral Letter"). Each type can be activated or deactivated. Documents uploaded to the platform are tagged with a document type.

**Templates:**
A template is tied to a document type and defines exactly what fields the AI should extract. For example, a template for "Insurance Card" might define fields like: `member_id`, `group_number`, `plan_name`, `effective_date`, `co_pay_amount`.

Each field definition in `extraction_fields` (stored as JSON) includes:
- The field name and label
- The expected data type
- Any extraction hints or rules for the AI

**Lifecycle:** Templates follow an active/inactive status. When a document is processed, the AI uses the template assigned to it. Admins can update templates without re-uploading documents — re-extraction can be triggered at any time.

**Who uses it:** System administrators and configuration managers who set up the platform for each type of document their organisation processes.

---

### Module 6 — Forms & Dynamic Data Entry

**What it does:**
This module provides a configurable data entry layer that can be attached to documents. Instead of hardcoding input fields, administrators can design custom forms with any combination of field types, and these forms appear alongside documents for manual data entry or verification.

**How it works:**

- An admin creates a **Form** with a name and description.
- They add **FormFields** to the form: each field has a type (text, number, email, select, checkbox, radio, date, textarea), a label, placeholder, required flag, options list (for select/radio/checkbox), and validation rules.
- One form can be marked as **active** at any time. The active form is the one that appears during document processing.
- When a user fills in the form for a document, the data is stored in `DocumentFormData` as a JSONB object linked to the document.

**Why it matters:** Different organisations process different types of documents and need to capture different information. The form builder allows each organisation to define their own data capture requirements without any code changes.

**Who uses it:** Admins design forms; document processors fill them in during document review.

---

### Module 7 — Standard Operating Procedures (SOPs)

**What it does:**
This module manages Standard Operating Procedures for healthcare providers. An SOP is a structured document that captures how a specific provider (clinic, doctor, facility) wants their billing, coding, and clinical workflows to be handled.

**What an SOP contains:**

| Section | Description |
|---|---|
| Provider Info | NPI, name, address, specialty, provider type (new/existing) |
| Workflow Process | Step-by-step workflow instructions specific to this provider |
| Billing Guidelines | Rules for how claims should be billed (modifiers, fee schedules, etc.) |
| Payer Guidelines | Insurance-specific rules for submitting claims to different payers |
| CPT Coding Rules | Rules for how CPT (procedure) codes should be assigned |
| ICD Coding Rules | Rules for how ICD (diagnosis) codes should be assigned |

**AI-Powered SOP Extraction:**
Supporting documents (PDFs, Word docs) can be uploaded to an SOP. The AI module reads these documents using `pdfminer.six` or `python-docx`, then sends the text to GPT-4o with a structured prompt. The AI extracts and organises the billing guidelines, payer rules, and coding rules from the unstructured document text and populates the SOP's JSONB fields automatically.

**Provider & Client Linking:**
Each SOP is linked to a client and optionally to one or more providers via the `SopProviderMapping` table. This means the system knows which SOP to apply when processing documents for that client-provider combination.

**Who uses it:** Billing specialists and operations managers who configure how each provider's work should be handled.

---

### Module 8 — Client Management

**What it does:**
This module manages the clients (typically healthcare providers — clinics, hospitals, physician practices) whose documents are processed by the platform. It is a complete CRM-style module for managing client data.

**Key functionality:**

- **Client Profile:** Each client has an NPI (National Provider Identifier), business name, contact details, specialty, and address. The NPI is used to look up provider information from the external NPI registry, auto-filling fields during client creation.
- **Multiple Locations:** A single client organisation can have multiple physical locations (e.g., a hospital group with several campuses). Each location has its own address stored in `ClientLocation`.
- **Provider Mapping:** Individual providers (physicians) are linked to clients. A provider can be associated with multiple client organisations, and each mapping can specify which location the provider works at.
- **User Assignment:** Platform users (e.g., billing specialists) are assigned to specific clients. This scoping ensures that a user only sees documents and data for the clients they manage.
- **Bulk Import:** Clients can be imported in bulk from an Excel or CSV file, making onboarding of a large client base fast and easy.
- **Soft Delete:** Clients are never permanently deleted — a `deleted_at` timestamp is set, hiding them from normal views while preserving their history.
- **Status Lifecycle:** Clients have an active/inactive status managed by the `Status` table.

**Who uses it:** Operations administrators who onboard and manage healthcare provider clients; users assigned to clients to process their documents.

---

### Module 9 — Organisation Management

**What it does:**
This module handles multi-tenancy. The platform supports multiple organisations (tenants), each completely isolated from each other. An organisation could be a billing company, a hospital group, or any business entity using the platform.

**How multi-tenancy works:**
Every major record in the database — users, documents, clients, roles, forms, SOPs — has an `organisation_id` foreign key. All queries are automatically scoped to the current user's organisation, so Organisation A can never see Organisation B's data.

**Key functionality:**

- **Create Organisations:** A superadmin creates new tenant organisations (e.g., onboarding a new billing company onto the platform).
- **Activate / Deactivate:** Organisations can be deactivated. When deactivated, all users in that organisation lose the ability to log in.
- **Organisation Selection (Superadmin):** The superadmin does not belong to any one organisation. They use a "select organisation" flow to temporarily enter an org's context, manage it, and then exit.
- **Statistics:** Org-level counts of users, documents, and clients are available for monitoring.

**Who uses it:** Superadmins only. Regular organisation admins cannot create or manage other organisations.

---

### Module 10 — Roles, Modules & RBAC (Permissions)

**What it does:**
This module controls what actions each user is allowed to take. Instead of hardcoding permissions per user, permissions are defined at the role level. A user inherits all permissions of their assigned role.

**The three-tier hierarchy:**

```
Organisation
    └── Role  (e.g., "Billing Specialist", "Supervisor", "Admin")
          ├── Module Access  (e.g., "Documents" → READ, CREATE)
          └── Submodule Access  (e.g., "Documents → Templates" → READ)
```

**Privilege types:**
- `READ` — can view/list data
- `CREATE` — can create new records
- `UPDATE` — can edit existing records
- `DELETE` — can remove records
- `MANAGE` — full CRUD
- `ADMIN` — full CRUD plus user/role management within the module

**How it is enforced:**
Every protected API route uses the `Permission` dependency. When a request arrives, the system:
1. Extracts the `role_id` from the JWT token.
2. Queries the `RoleModule` and `RoleSubmodule` tables to check if the role has the required privilege for the requested module.
3. Returns `403 Forbidden` if not authorised.
4. Superusers bypass all checks.

**Default Roles:** Roles can be marked as `is_default = True`, meaning new users are automatically assigned that role. Roles marked `can_edit = False` are system roles that cannot be modified.

**Who uses it:** Configured by organisation admins. Enforced automatically on every API call.

**RBAC Permission Model Diagram:**

```mermaid
graph TD
    Org(["Organisation"])
    User(["User"])
    Role(["Role\ne.g. Billing Specialist"])
    RM["RoleModule\njunction table"]
    RS["RoleSubmodule\njunction table"]
    Mod["Module\ne.g. documents"]
    Sub["Submodule\ne.g. templates"]
    Priv["Privilege\nREAD · CREATE · UPDATE\nDELETE · MANAGE · ADMIN"]

    Org --> Role
    User -->|"assigned via UserRole"| Role
    Role --> RM
    Role --> RS
    RM --> Mod
    RM --> Priv
    RS --> Sub
    RS --> Priv

    Req(["Incoming API Request"])
    Check{"Permission.check()\nmodule + privilege"}
    Allow(["✓ 200 OK\nRequest proceeds"])
    Deny(["✗ 403 Forbidden"])
    Super(["is_superuser = True\nBypasses all checks"])

    Req --> Check
    Check -->|"role has privilege"| Allow
    Check -->|"role lacks privilege"| Deny
    Check -->|"superuser flag"| Super
    Super --> Allow
```

---

### Module 11 — Webhook Integration

**What it does:**
This module allows external systems to be notified in real-time when events happen inside the platform. For example, an external billing system could be notified every time a new document is processed.

**How it works:**

1. A user creates a webhook by providing a target URL, a signing secret, and a list of event names they want to subscribe to (e.g., `document.processed`, `client.created`).
2. When the subscribed event occurs, the platform sends an HTTP POST request to the webhook URL with a JSON payload describing the event.
3. The payload is signed using the webhook secret (HMAC) so the receiving system can verify the request is genuine.
4. Webhooks can be activated or deactivated without deletion.

**Why it matters:** Webhooks are the integration layer between the docucr platform and external tools. They enable automation pipelines, real-time data sync with billing systems, and notifications to third-party dashboards.

**Who uses it:** Developers and integration engineers who connect the platform to external systems.

---

### Module 12 — Activity Logging (Audit Trail)

**What it does:**
Every significant action performed by any user on the platform is recorded in the `activity_logs` table. This creates a complete, tamper-evident audit trail that can be used for compliance, debugging, and accountability.

**What is logged:**

| Field | Example |
|---|---|
| `action` | `CREATE`, `UPDATE`, `DELETE`, `LOGIN`, `SHARE`, `DOWNLOAD` |
| `entity_type` | `Document`, `User`, `Client`, `Role`, `SOP` |
| `entity_id` | The ID of the affected record |
| `details` | JSON with before/after values or context |
| `user_id` | Who performed the action |
| `organisation_id` | Which organisation the action occurred in |
| `ip_address` | The caller's IP address |
| `user_agent` | The browser/client string |
| `created_at` | Exact timestamp |

**Filtering:** Logs can be filtered by action type, entity type, user name, date range, and entity ID to quickly find what you're looking for.

**Who uses it:** Organisation administrators for compliance reviews; developers for debugging; auditors for accountability checks.

---

### Module 13 — Printer Management

**What it does:**
This module allows users to configure network printers and print documents directly from the platform without saving files locally or using external print dialogs.

**Key functionality:**

- **Configure Printers:** Admins add printers by specifying their IP address, port (default: 9100), and protocol (RAW/IPP/LPD).
- **Test Connection:** Before saving, the connection to the printer can be tested to verify reachability.
- **Auto-Discovery:** The platform uses mDNS/Zeroconf to automatically discover printers available on the local network, eliminating the need to know the IP address in advance.
- **Print Documents:** A document stored in S3 can be sent directly to a configured printer via the API. The document is downloaded from S3 and sent to the printer using the configured protocol.
- **Status Tracking:** Each printer has a status: `ACTIVE`, `INACTIVE`, or `ERROR`.

**Protocols supported:**

| Protocol | Description |
|---|---|
| RAW | Direct socket printing on port 9100 (most common for network printers) |
| IPP | Internet Printing Protocol |
| LPD | Line Printer Daemon protocol |

**Who uses it:** Office staff who need to print physical copies of processed documents.

---

### Module 14 — Dashboard & Statistics

**What it does:**
This module provides aggregated KPI data to give administrators and users a high-level view of platform activity and performance.

**Admin Dashboard:**
- Total documents uploaded (today, this week, this month)
- Document counts by status (processed, pending, error)
- User counts (total, active, inactive)
- Client counts
- Document throughput over time (charts)
- Processing accuracy metrics

**User Dashboard:**
- Documents assigned to this user
- Documents pending review
- Documents completed today
- Extraction accuracy rate for this user's documents
- Recent activity timeline

**Why it matters:** The dashboard gives managers visibility into team productivity and system health without needing to query the database directly.

**Who uses it:** Admins see the admin dashboard; regular users see their personal dashboard.

---

### Module 15 — External Document Sharing

**What it does:**
This module allows platform users to share documents with people who do not have a platform account — for example, sharing a processed insurance card with the patient or an extracted report with an external auditor.

**How it works:**

1. A user creates an external share for a document, providing the recipient's email address, a password, and an expiry time.
2. The system generates a unique random token and stores it along with the bcrypt-hashed password.
3. The generated URL (e.g., `https://platform.example.com/public/share/<token>`) is sent to the recipient.
4. The recipient opens the URL — they are shown a password prompt.
5. They enter the password — the backend verifies it against the bcrypt hash.
6. If correct and not expired, the document is displayed (or available for download).

**Security features:**
- Passwords are never stored in plain text — bcrypt hashing is used.
- Links expire at a configurable time — after expiry, the document is no longer accessible via the link.
- No account creation required by the recipient.

**Who uses it:** Document processors who need to share processed data with external parties securely.

---

## Tech Stack

| Category | Library / Tool | Version |
|---|---|---|
| Framework | FastAPI | 0.104.0+ |
| Server | Uvicorn | 0.24.0+ |
| Language | Python | 3.11 |
| Database | PostgreSQL | 14+ |
| ORM | SQLAlchemy | 2.0.23+ |
| DB Driver | psycopg2-binary | 2.9.9+ |
| Migrations | Alembic | 1.13.0+ |
| Auth (JWT) | python-jose[cryptography] | 3.3.0+ |
| Auth (Bcrypt) | passlib[bcrypt] | <1.8 |
| Bcrypt | bcrypt | <4.0 |
| Object Storage | boto3 (AWS S3) | 1.34.0+ |
| AI/ML | openai | 1.3.0+ |
| PDF parsing | pdfminer.six | 20221105+ |
| PDF to images | pdf2image | 1.16.3+ |
| OCR | pytesseract | 0.3.10+ |
| Image processing | Pillow | 10.0.0+ |
| Word docs | python-docx | 0.8.11+ |
| PDF generation | reportlab | 4.0.0+ |
| HTML to PDF | weasyprint | 61.0+ |
| Excel | openpyxl | 3.1.0+ |
| Data manipulation | pandas | 2.0.0+ |
| Data validation | pydantic[email] | 2.5.0+ |
| File upload | python-multipart | 0.0.6+ |
| Phone validation | phonenumbers | 8.13.0+ |
| Templating | jinja2 | 3.1.0+ |
| Real-time | websockets | 12.0+ |
| mDNS discovery | zeroconf | 0.131.0+ |
| HTTP client | requests | 2.31.0+ |
| Env vars | python-dotenv | 1.0.0+ |

---

## Project Structure

```text
docucr-backend/
├── alembic/                    # Alembic database migration tool
│   ├── versions/               # Auto-generated migration scripts
│   │   ├── 0001_baseline.py    # Initial schema
│   │   ├── 0002_*.py           # Subsequent incremental migrations
│   │   └── ...
│   ├── env.py                  # Alembic environment config (uses DATABASE_URL)
│   └── script.py.mako          # Migration script template
├── app/                        # Main application package
│   ├── core/                   # Core infrastructure
│   │   ├── database.py         # SQLAlchemy engine, SessionLocal, get_db() dependency
│   │   ├── security.py         # JWT creation/validation, bcrypt hashing, auth dependencies
│   │   └── permissions.py      # RBAC Permission class — module/submodule/privilege checking
│   ├── models/                 # SQLAlchemy ORM models (40+ tables)
│   │   ├── user.py             # User model
│   │   ├── role.py             # Role model
│   │   ├── privilege.py        # Privilege model
│   │   ├── module.py           # Module model
│   │   ├── submodule.py        # Submodule model
│   │   ├── organisation.py     # Organisation model
│   │   ├── user_role.py        # UserRole junction table
│   │   ├── role_module.py      # RoleModule junction table
│   │   ├── role_submodule.py   # RoleSubmodule junction table
│   │   ├── user_client.py      # UserClient junction table
│   │   ├── user_role_module.py # Fine-grained user-module access
│   │   ├── document.py         # Document model
│   │   ├── document_type.py    # DocumentType model
│   │   ├── template.py         # Template (extraction schema) model
│   │   ├── extracted_document.py     # ExtractedDocument model
│   │   ├── unverified_document.py    # UnverifiedDocument model
│   │   ├── document_form_data.py     # DocumentFormData model
│   │   ├── document_share.py   # DocumentShare (internal) model
│   │   ├── external_share.py   # ExternalShare (token link) model
│   │   ├── form.py             # Form model
│   │   ├── client.py           # Client model
│   │   ├── client_location.py  # ClientLocation model
│   │   ├── provider.py         # Provider model
│   │   ├── provider_client_mapping.py  # ProviderClientMapping model
│   │   ├── activity_log.py     # ActivityLog audit model
│   │   ├── sop.py              # SOP model
│   │   ├── sop_document.py     # SOPDocument model
│   │   ├── sop_provider_mapping.py   # SopProviderMapping model
│   │   ├── status.py           # Status (lookup) model
│   │   ├── webhook.py          # Webhook model
│   │   ├── printer.py          # Printer model
│   │   ├── otp.py              # OTP model
│   │   └── user_supervisor.py  # UserSupervisor mapping
│   ├── routers/                # FastAPI APIRouter modules (20+ routers)
│   │   ├── auth.py             # /api/auth routes
│   │   ├── users.py            # /api/users routes
│   │   ├── documents.py        # /api/documents routes
│   │   ├── document_ai.py      # /api/document-ai routes
│   │   ├── document_types.py   # /api/document-types routes
│   │   ├── templates.py        # /api/templates routes
│   │   ├── forms.py            # /api/forms routes
│   │   ├── clients.py          # /api/clients routes
│   │   ├── organisations.py    # /api/organisations routes
│   │   ├── roles.py            # /api/roles routes
│   │   ├── privileges.py       # /api/privileges routes
│   │   ├── modules.py          # /api/modules routes
│   │   ├── statuses.py         # /api/statuses routes
│   │   ├── profile.py          # /api/profile routes
│   │   ├── webhooks.py         # /api/webhooks routes
│   │   ├── sops.py             # /api/sops routes
│   │   ├── printers.py         # /api/printers routes
│   │   ├── activity_log.py     # /api/activity-log routes
│   │   ├── dashboard.py        # /api/dashboard routes
│   │   ├── migration.py        # /api/migration routes
│   │   └── external_share.py   # /api/external-share routes
│   ├── services/               # Business logic layer (25+ services)
│   │   ├── auth_service.py     # Authentication, OTP, token generation
│   │   ├── user_service.py     # User CRUD, role assignment, client mapping
│   │   ├── document_service.py # Document upload, processing, S3 integration
│   │   ├── ai_sop_service.py   # AI-powered SOP extraction with GPT-4o
│   │   ├── s3_service.py       # AWS S3 operations
│   │   ├── webhook_service.py  # Webhook CRUD and event dispatch
│   │   ├── activity_service.py # Audit logging
│   │   ├── form_service.py     # Form and field management
│   │   ├── client_service.py   # Client, location, provider management
│   │   ├── document_share_service.py  # Internal document sharing
│   │   ├── external_share_service.py  # External link sharing
│   │   ├── dashboard_service.py # Dashboard statistics
│   │   ├── organisations_service.py   # Organisation management
│   │   ├── role_service.py     # Role and permission management
│   │   ├── document_type_service.py   # Document type management
│   │   ├── template_service.py # Extraction template management
│   │   ├── sop_service.py      # SOP management
│   │   ├── printer_service.py  # Printer CRUD and print operations
│   │   └── migration_service.py # Document migration
│   ├── utils/                  # Utility functions
│   │   └── email.py            # SMTP email sender (OTP emails, notifications)
│   ├── templates/              # Jinja2 templates
│   │   ├── email/              # Email HTML templates (OTP, notifications)
│   │   └── pdf/                # PDF generation templates
│   └── main.py                 # FastAPI app init, router registration, CORS config
├── tests/                      # Pytest test suites
│   ├── conftest.py             # Test fixtures, DB setup, test client
│   └── test_*.py               # Feature-specific test files
├── deploy/                     # Infrastructure-as-Code and deployment
│   └── terraform/              # Terraform configs (AWS, networking, etc.)
├── alembic.ini                 # Alembic migration configuration file
├── app.py                      # Wrapper entry point (runs uvicorn)
├── main.py                     # Top-level entry alias
├── run_seed.py                 # Seeds Roles, Modules, Privileges, Statuses
├── sync_master_data.py         # Loads master/reference data
├── generate_jwt_secret.py      # Utility to generate a JWT secret key
├── requirements.txt            # All Python dependencies with pinned versions
├── Dockerfile                  # Docker container definition
└── .env.example                # Environment variable template
```

---

## Database Models

> Database schema is created under the PostgreSQL schema `docucr` (configurable via `DB_SCHEMA`).

### Identity & Access Models

#### `users` — User
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | UUID string |
| email | String(255) | unique, indexed | Login identifier |
| username | String(100) | unique | Display name |
| hashed_password | String | — | Bcrypt hash |
| first_name | String(100) | — | |
| middle_name | String(100) | nullable | |
| last_name | String(100) | — | |
| phone_country_code | String(10) | nullable | e.g. "+1" |
| phone_number | String(20) | nullable | |
| is_superuser | Boolean | default False | Bypasses all RBAC |
| is_supervisor | Boolean | default False | Supervisor hierarchy |
| is_client | Boolean | default False | Client-type user |
| client_id | UUID FK | nullable | → Client |
| status_id | Integer FK | — | → Status |
| organisation_id | String FK | nullable | → Organisation |
| profile_image_url | String | nullable | S3 URL |
| created_at | DateTime(tz) | server_default | |
| updated_at | DateTime(tz) | onupdate | |
| created_by | String FK | nullable | → User (self-ref) |

**Relationships:** creator, organisation, roles (via UserRole), documents_created, shared_documents

---

#### `roles` — Role
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | UUID string |
| name | String(50) | — | Unique per org |
| description | Text | nullable | |
| is_default | Boolean | default False | Auto-assigned to new users |
| can_edit | Boolean | default True | Whether role is editable |
| status_id | Integer FK | — | → Status |
| organisation_id | String FK | — | → Organisation |
| created_at | DateTime | server_default | |
| updated_at | DateTime | onupdate | |
| created_by | String FK | nullable | → User |

**Unique constraint:** `(name, organisation_id)`

---

#### `privileges` — Privilege
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | |
| name | String | unique | e.g. READ, CREATE, UPDATE, DELETE, MANAGE, ADMIN |
| description | Text | nullable | |
| created_at | DateTime | — | |
| updated_at | DateTime | — | |

---

#### `modules` — Module
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | |
| name | String | unique | Internal identifier |
| label | String | — | Display name |
| route | String | — | Frontend route path |
| icon | String | nullable | Icon name |
| category | String | nullable | Grouping category |
| description | Text | nullable | |
| has_submodules | Boolean | default False | |
| submodules | JSON | nullable | List of submodule keys |
| is_active | Boolean | default True | |
| display_order | Integer | default 0 | Sidebar ordering |
| color_from | String | nullable | Gradient start color |
| color_to | String | nullable | Gradient end color |
| color_shadow | String | nullable | Shadow color |
| created_at | DateTime | — | |
| updated_at | DateTime | — | |

---

#### `submodules` — Submodule
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | |
| module_id | String FK | — | → Module |
| name | String | — | Internal key |
| label | String | — | Display name |
| route_key | String | — | Sub-path key |
| display_order | Integer | default 0 | |
| created_at | DateTime | — | |
| updated_at | DateTime | — | |

---

#### `organisations` — Organisation
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | String | PK | |
| name | String | — | |
| status_id | Integer FK | — | → Status |
| created_at | DateTime | — | |

**Relationships:** users, status_relation

---

### Junction / Mapping Tables

#### `user_roles` — UserRole
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| user_id | String FK | → User |
| role_id | String FK | → Role |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `role_modules` — RoleModule
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| role_id | String FK | → Role |
| module_id | String FK | → Module |
| privilege_id | String FK | → Privilege |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `role_submodules` — RoleSubmodule
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| role_id | String FK | → Role |
| submodule_id | String FK | → Submodule |
| privilege_id | String FK | → Privilege |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `user_clients` — UserClient
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| user_id | String FK | → User |
| client_id | UUID FK | → Client |
| assigned_by | String FK | → User |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |

**Unique constraint:** `(user_id, client_id)`

---

#### `user_role_modules` — UserRoleModule
Fine-grained user-specific module access overrides per role.

| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| user_id | String FK | → User |
| role_id | String FK | → Role |
| module_id | String FK | → Module |
| privilege_id | String FK | → Privilege |
| created_at | DateTime | |

---

### Document Models

#### `documents` — Document
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK, autoincrement | |
| filename | String(255) | — | Storage filename |
| original_filename | String(255) | — | User's original filename |
| file_size | Integer | — | Bytes |
| content_type | String(100) | — | MIME type |
| s3_key | String | — | S3 object key |
| s3_bucket | String | — | S3 bucket name |
| status_id | Integer FK | — | → Status |
| upload_progress | Integer | 0–100 | Upload percentage |
| error_message | Text | nullable | Upload/processing error |
| analysis_report_s3_key | String | nullable | S3 key for AI report |
| is_archived | Boolean | default False | |
| total_pages | Integer | nullable | PDF page count |
| document_type_id | UUID FK | nullable | → DocumentType |
| template_id | UUID FK | nullable | → Template |
| client_id | UUID FK | nullable | → Client |
| enable_ai | Boolean | default True | Whether to run AI extraction |
| organisation_id | String FK | — | → Organisation |
| created_by | String FK | — | → User |
| created_at | DateTime(tz) | server_default | |
| updated_at | DateTime(tz) | onupdate | |

**Relationships:** creator, status, client, extracted_documents, unverified_documents, shares, form_data_relation

---

#### `document_types` — DocumentType
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | String(100) | |
| description | Text | nullable |
| status_id | Integer FK | → Status |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |
| updated_at | DateTime | |

**Relationships:** templates

---

#### `templates` — Template
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| template_name | String(100) | |
| description | Text | nullable |
| document_type_id | UUID FK | → DocumentType |
| status_id | Integer FK | → Status |
| extraction_fields | JSON | default [] — list of field extraction rules |
| created_by | String FK | → User |
| updated_by | String FK | → User, nullable |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |
| updated_at | DateTime | |

**Unique constraint:** `(template_name, document_type_id)`

---

#### `extracted_documents` — ExtractedDocument
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | Integer FK | → Document |
| document_type_id | UUID FK | → DocumentType |
| template_id | UUID FK | nullable → Template |
| page_range | String | e.g. "1-3" |
| extracted_data | JSON | Key-value pairs of extracted fields |
| confidence | Float | 0.0–1.0 confidence score |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `unverified_documents` — UnverifiedDocument
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | Integer FK | → Document |
| suspected_type | String(100) | AI-suggested document type |
| page_range | String | |
| extracted_data | JSON | Preliminary extracted fields |
| status | String | PENDING / VERIFIED / REJECTED |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `document_form_data` — DocumentFormData
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | |
| document_id | Integer FK | → Document (unique — one form per doc) |
| form_id | String FK | → Form |
| data | JSONB | Form field values |
| created_at | DateTime | |
| updated_at | DateTime | |

---

### Sharing Models

#### `document_shares` — DocumentShare (internal)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | Integer FK | → Document (indexed) |
| user_id | String FK | → User (indexed) |
| shared_by_user_id | String FK | → User |
| shared_by_org_id | String FK | → Organisation |
| created_at | DateTime | |

**Unique constraint:** `(document_id, user_id)`

---

#### `external_shares` — ExternalShare (public token links)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | Integer FK | → Document |
| email | String | Recipient email |
| password_hash | String | Bcrypt-hashed access password |
| token | String | unique, indexed — URL token |
| shared_by_user_id | String FK | → User |
| shared_by_org_id | String FK | → Organisation |
| expires_at | DateTime | Expiry timestamp |
| created_at | DateTime | |

---

### Form Models

#### `forms` — Form
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| name | String(100) | indexed |
| description | Text | nullable |
| status_id | Integer FK | → Status |
| created_by | String FK | → User |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `form_fields` — FormField
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| form_id | String FK | → Form (cascade delete) |
| field_type | String | text / textarea / number / email / select / checkbox / radio / date |
| label | String(200) | |
| placeholder | String(200) | nullable |
| required | Boolean | default False |
| default_value | JSON | nullable |
| options | JSON | nullable — for select/radio/checkbox |
| validation | JSON | nullable — validation rules |
| order | Integer | Display order |
| is_system | Boolean | default False — system fields cannot be deleted |
| created_at | DateTime | |

---

### Client Models

#### `clients` — Client
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID PK | | |
| business_name | String | nullable | |
| first_name | String | — | |
| middle_name | String | nullable | |
| last_name | String | nullable | |
| npi | String(10) | indexed | National Provider Identifier |
| type | String(50) | nullable | Provider type |
| address_line_1 | String | nullable | |
| address_line_2 | String | nullable | |
| city | String | nullable | |
| state_code | String(2) | check: len=2 | |
| state_name | String | nullable | |
| country | String | nullable | |
| zip_code | String(9) | check: ^\d{5}-\d{4}$ | |
| specialty | String | nullable | Medical specialty |
| specialty_code | String | nullable | |
| is_user | Boolean | default False | Whether client has a user account |
| description | Text | nullable | |
| created_by | String FK | — | → User |
| status_id | Integer FK | — | → Status |
| organisation_id | String FK | — | → Organisation |
| deleted_at | DateTime | nullable | Soft delete |
| created_at | DateTime | — | |
| updated_at | DateTime | — | |

**Properties:** `statusCode`, `status_code`, `assigned_users`

---

#### `client_locations` — ClientLocation
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| client_id | UUID FK | → Client |
| address_line_1 | String | |
| address_line_2 | String | nullable |
| city | String | |
| state_code | String(2) | |
| state_name | String | nullable |
| country | String | nullable |
| zip_code | String(9) | |
| is_primary | Boolean | default False |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `providers` — Provider
| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID PK | | |
| first_name | String | required | |
| middle_name | String | nullable | |
| last_name | String | nullable | |
| npi | String | unique, indexed | |
| ptan_id | String | unique, indexed | nullable |
| address_line_1 | String | nullable | |
| address_line_2 | String | nullable | |
| city | String | nullable | |
| state_code | String(2) | check: len=2 | |
| state_name | String | nullable | |
| country | String | nullable | |
| zip_code | String | check: ^\d{5}-\d{4}$ | nullable |
| created_by | String FK | — | → User |
| created_at | DateTime | — | |

---

#### `provider_client_mappings` — ProviderClientMapping
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider_id | UUID FK | → Provider |
| client_id | UUID FK | → Client |
| location_id | UUID FK | nullable → ClientLocation |
| created_at | DateTime | |

---

### Activity & Audit Models

#### `activity_logs` — ActivityLog
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | auto-generated |
| user_id | String FK | nullable → User (lazy-loaded) |
| organisation_id | String FK | nullable → Organisation (lazy-loaded) |
| action | String | indexed — e.g. "CREATE", "UPDATE", "DELETE", "LOGIN" |
| entity_type | String | indexed — e.g. "Document", "User", "Client" |
| entity_id | String | nullable — ID of affected entity |
| details | JSON | Arbitrary details dict |
| ip_address | Text | nullable — caller IP |
| user_agent | Text | nullable — browser/client string |
| created_at | DateTime | indexed |

---

### SOP Models

#### `sops` — SOP
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| title | String | |
| category | String | nullable |
| provider_type | String | "new" or "existing" |
| client_id | UUID FK | nullable → Client |
| provider_info | JSONB | nullable |
| workflow_process | JSONB | nullable |
| billing_guidelines | JSONB | nullable |
| payer_guidelines | JSONB | nullable |
| coding_rules_cpt | JSONB | default [] |
| coding_rules_icd | JSONB | default [] |
| status_id | Integer FK | → Status (lifecycle: ACTIVE/INACTIVE) |
| workflow_status_id | Integer FK | → Status (processing state) |
| created_by | String FK | → User |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |
| updated_at | DateTime | |

**Relationships:** client, creator, organisation, documents (SOPDocument), provider_mappings

---

#### `sop_documents` — SOPDocument
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| sop_id | UUID FK | → SOP (cascade delete) |
| name | String | |
| category | String | e.g. "SOURCE_FILE" |
| s3_key | String | |
| billing_guidelines | JSONB | nullable |
| payer_guidelines | JSONB | nullable |
| coding_rules_cpt | JSONB | nullable |
| coding_rules_icd | JSONB | nullable |
| processed | Boolean | default False |
| created_at | DateTime | |

---

#### `sop_provider_mappings` — SopProviderMapping
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| sop_id | UUID FK | → SOP |
| provider_id | UUID FK | → Provider |
| created_at | DateTime | |

---

### System Models

#### `statuses` — Status
| Field | Type | Notes |
|---|---|---|
| id | Integer PK | |
| code | String | unique, indexed — e.g. "ACTIVE", "INACTIVE", "PENDING" |
| description | Text | nullable |
| type | String | Grouping — e.g. "user", "document", "sop" |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `webhooks` — Webhook
| Field | Type | Notes |
|---|---|---|
| id | String PK | UUID |
| user_id | String FK | → User |
| name | String(100) | |
| url | String(500) | Target URL |
| secret | String(255) | Signing secret |
| events | JSON | List of event names to subscribe to |
| is_active | Boolean | default True |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `printers` — Printer
| Field | Type | Notes |
|---|---|---|
| id | String PK | UUID |
| name | String | |
| ip_address | String | |
| port | Integer | default 9100 |
| protocol | String | RAW / IPP / LPD |
| description | String | nullable |
| status | String | ACTIVE / INACTIVE / ERROR |
| created_at | DateTime | |
| updated_at | DateTime | |

---

#### `otps` — OTP
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| email | String | indexed |
| otp_code | String | 6-digit code |
| purpose | String | RESET / LOGIN |
| is_used | Boolean | default False |
| expires_at | DateTime | |
| created_at | DateTime | |

---

#### `user_supervisors` — UserSupervisor
| Field | Type | Notes |
|---|---|---|
| id | String PK | |
| user_id | String FK | → User (supervised) |
| supervisor_id | String FK | → User (supervisor) |
| organisation_id | String FK | → Organisation |
| created_at | DateTime | |

---

## API Endpoints

All endpoints are prefixed with `/api`. Protected routes require `Authorization: Bearer <token>` header.

### Auth — `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | Public | Authenticate with email + password. Returns temp token (superadmin) or initiates 2FA OTP |
| POST | `/api/auth/verify-2fa` | Public | Verify OTP code sent to email. Returns access + refresh tokens (or prompts role selection) |
| POST | `/api/auth/resend-2fa` | Public | Resend OTP to email for 2FA |
| POST | `/api/auth/select-role` | Temp/JWT | Select organisation and role; returns final access + refresh tokens |
| POST | `/api/auth/forgot-password` | Public | Send password reset OTP to email |
| POST | `/api/auth/reset-password` | Public | Reset password using email + OTP + new password |
| POST | `/api/auth/refresh` | Refresh token | Exchange refresh token for new access token |

---

### Users — `/api/users`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/users` | JWT | List users. Query params: `page`, `page_size`, `search`, `status_id`, `role_id`, `organisation_id`, `client_id`, `created_by`, `is_client` |
| GET | `/api/users/creators` | JWT | Lightweight list of users for creator dropdowns |
| GET | `/api/users/me` | JWT | Get current authenticated user's profile |
| GET | `/api/users/by-organisation` | JWT | Get users belonging to a specific organisation |
| GET | `/api/users/by-client` | JWT | Get users assigned to a specific client |
| GET | `/api/users/share/users` | JWT | Get users eligible for document sharing |
| GET | `/api/users/stats` | JWT | User statistics (total, active, inactive counts) |
| GET | `/api/users/by-role/{role_id}` | JWT | Get users assigned to a specific role |
| GET | `/api/users/email/{email}` | JWT | Get a user by their email address |
| GET | `/api/users/{user_id}` | JWT | Get a single user by ID |
| POST | `/api/users` | JWT | Create a new user |
| PUT | `/api/users/{user_id}` | JWT | Update user details |
| POST | `/api/users/{user_id}/activate` | JWT | Activate a deactivated user |
| POST | `/api/users/{user_id}/deactivate` | JWT | Deactivate an active user |
| POST | `/api/users/{user_id}/change-password` | JWT | Admin-forced password change for a user |
| GET | `/api/users/{user_id}/clients` | JWT | Get clients mapped to a user |
| POST | `/api/users/{user_id}/clients` | JWT | Map one or more clients to a user |
| POST | `/api/users/unassign-clients` | JWT | Unassign clients from a user |

---

### Documents — `/api/documents`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/documents/upload` | JWT | Upload one or more documents (multipart/form-data). Supports progress tracking |
| GET | `/api/documents` | JWT | List documents with filters: `status_id`, `document_type_id`, `client_id`, `template_id`, `search`, `page`, `page_size`, `is_archived` |
| GET | `/api/documents/{id}` | JWT | Get document detail including extracted data |
| PUT | `/api/documents/{id}` | JWT | Update document metadata |
| DELETE | `/api/documents/{id}` | JWT | Delete a document |
| POST | `/api/documents/{id}/archive` | JWT | Archive a document |
| POST | `/api/documents/{id}/unarchive` | JWT | Unarchive a document |
| GET | `/api/documents/{id}/download` | JWT | Download document file from S3 |
| GET | `/api/documents/shared-with-me` | JWT | Get documents shared with the current user |
| POST | `/api/documents/share` | JWT | Share documents with users (internal share) |

---

### Document AI — `/api/document-ai`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/document-ai/classify-and-extract` | JWT | Run AI classification and field extraction on a document using GPT-4o |

---

### Document Types — `/api/document-types`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/document-types` | JWT | List all document types |
| GET | `/api/document-types/{id}` | JWT | Get a document type by ID |
| POST | `/api/document-types` | JWT | Create a document type |
| PUT | `/api/document-types/{id}` | JWT | Update a document type |
| POST | `/api/document-types/{id}/activate` | JWT | Activate a document type |
| POST | `/api/document-types/{id}/deactivate` | JWT | Deactivate a document type |

---

### Templates — `/api/templates`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/templates` | JWT | List templates. Query: `document_type_id`, `status_id`, `page`, `page_size` |
| GET | `/api/templates/{id}` | JWT | Get template with extraction fields |
| POST | `/api/templates` | JWT | Create a new extraction template |
| PUT | `/api/templates/{id}` | JWT | Update template name, description, or extraction fields |
| DELETE | `/api/templates/{id}` | JWT | Delete a template |

---

### Forms — `/api/forms`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/forms` | JWT | List forms. Query: `page`, `page_size`, `status` |
| GET | `/api/forms/stats` | JWT | Form statistics (total, active counts) |
| GET | `/api/forms/active` | JWT | Get the currently active form |
| GET | `/api/forms/{id}` | JWT | Get form with all its fields |
| POST | `/api/forms` | JWT | Create a form |
| PUT | `/api/forms/{id}` | JWT | Update form and its fields |
| DELETE | `/api/forms/{id}` | JWT | Delete a form |

---

### Clients — `/api/clients`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/clients` | JWT | List clients. Query: `search`, `status_id`, `page`, `page_size` |
| GET | `/api/clients/npi-lookup/{npi}` | JWT | Look up provider details from NPI registry |
| GET | `/api/clients/{id}` | JWT | Get client detail |
| POST | `/api/clients` | JWT | Create a client |
| PUT | `/api/clients/{id}` | JWT | Update a client |
| DELETE | `/api/clients/{id}` | JWT | Soft-delete a client |
| GET | `/api/clients/stats` | JWT | Client statistics |
| GET | `/api/clients/{id}/users` | JWT | Get users assigned to a client |
| POST | `/api/clients/{id}/assign-users` | JWT | Assign users to a client |
| GET | `/api/clients/{id}/locations` | JWT | Get client locations |
| POST | `/api/clients/{id}/locations` | JWT | Add a location to a client |
| PUT | `/api/clients/{id}/locations/{loc_id}` | JWT | Update a client location |
| DELETE | `/api/clients/{id}/locations/{loc_id}` | JWT | Delete a client location |
| GET | `/api/clients/{id}/providers` | JWT | Get providers mapped to a client |
| POST | `/api/clients/{id}/providers` | JWT | Map a provider to a client |
| POST | `/api/clients/import` | JWT | Bulk import clients from a file |

---

### Organisations — `/api/organisations`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/organisations` | JWT | List organisations. Query: `page`, `page_size`, `search`, `status_id` |
| GET | `/api/organisations/{id}` | JWT | Get an organisation |
| GET | `/api/organisations/stats` | JWT | Organisation statistics |
| POST | `/api/organisations` | JWT | Create an organisation |
| PUT | `/api/organisations/{id}` | JWT | Update an organisation |
| POST | `/api/organisations/{id}/activate` | JWT | Activate an organisation |
| POST | `/api/organisations/{id}/deactivate` | JWT | Deactivate an organisation |
| POST | `/api/organisations/select-organisation/{org_id}` | Temp JWT | Superadmin selects an organisation to manage |
| POST | `/api/organisations/exit-organisation` | JWT | Superadmin exits current org session |

---

### Roles — `/api/roles`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/roles` | JWT | List roles. Query: `page`, `page_size`, `status_id`, `search`, `organisation_id` |
| GET | `/api/roles/light` | JWT | Lightweight role list for dropdowns |
| GET | `/api/roles/assignable` | JWT | Roles that can be assigned to users |
| GET | `/api/roles/stats` | JWT | Role statistics |
| GET | `/api/roles/{id}` | JWT | Get role details |
| GET | `/api/roles/{id}/modules` | JWT | Get module permissions for a role |
| GET | `/api/roles/{id}/users` | JWT | Get users assigned to a role |
| POST | `/api/roles` | JWT | Create a role |
| PUT | `/api/roles/{id}` | JWT | Update role and module permissions |
| DELETE | `/api/roles/{id}` | JWT | Delete a role |

---

### Privileges — `/api/privileges`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/privileges` | JWT | List all available privileges |
| GET | `/api/privileges/{id}` | JWT | Get a privilege by ID |
| POST | `/api/privileges` | JWT | Create a privilege |
| PUT | `/api/privileges/{id}` | JWT | Update a privilege |
| DELETE | `/api/privileges/{id}` | JWT | Delete a privilege |

---

### Modules — `/api/modules`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/modules` | JWT | List all modules |
| GET | `/api/modules/user-modules` | JWT | Get modules accessible to a user (by email). Query: `email` |
| GET | `/api/modules/{id}` | JWT | Get a module with its submodules |
| POST | `/api/modules` | JWT | Create a module |
| PUT | `/api/modules/{id}` | JWT | Update a module |
| DELETE | `/api/modules/{id}` | JWT | Delete a module |

---

### Statuses — `/api/statuses`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/statuses` | JWT | List all statuses. Query: `type` filter |
| GET | `/api/statuses/{id}` | JWT | Get a status by ID |
| POST | `/api/statuses` | JWT | Create a status |
| PUT | `/api/statuses/{id}` | JWT | Update a status |

---

### Profile — `/api/profile`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/profile` | JWT | Get current user's profile |
| PUT | `/api/profile` | JWT | Update profile fields (name, phone, etc.) |
| POST | `/api/profile/upload-image` | JWT | Upload profile picture to S3 |
| POST | `/api/profile/change-password` | JWT | Change own password |

---

### Webhooks — `/api/webhooks`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/webhooks` | JWT | List webhooks for the current user |
| POST | `/api/webhooks` | JWT | Create a webhook |
| GET | `/api/webhooks/{id}` | JWT | Get a webhook |
| PATCH | `/api/webhooks/{id}` | JWT | Update webhook URL, name, secret, or events |
| DELETE | `/api/webhooks/{id}` | JWT | Delete a webhook |

---

### SOPs — `/api/sops`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sops` | JWT | List SOPs. Query: `search`, `status`, `start_date`, `end_date`, `page`, `page_size` |
| GET | `/api/sops/stats` | JWT | SOP statistics |
| GET | `/api/sops/{id}` | JWT | Get SOP detail with documents and provider mappings |
| POST | `/api/sops` | JWT | Create an SOP |
| PUT | `/api/sops/{id}` | JWT | Update an SOP |
| DELETE | `/api/sops/{id}` | JWT | Delete an SOP |
| POST | `/api/sops/{id}/documents` | JWT | Upload a supporting document to an SOP |
| POST | `/api/sops/{id}/documents/{doc_id}/process` | JWT | Trigger AI extraction on an SOP document |
| DELETE | `/api/sops/{id}/documents/{doc_id}` | JWT | Remove a document from an SOP |
| POST | `/api/sops/{id}/providers` | JWT | Map a provider to an SOP |
| DELETE | `/api/sops/{id}/providers/{mapping_id}` | JWT | Unmap a provider from an SOP |

---

### Printers — `/api/printers`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/printers` | JWT | List configured printers |
| POST | `/api/printers` | JWT | Add a printer |
| GET | `/api/printers/{id}` | JWT | Get printer details |
| PUT | `/api/printers/{id}` | JWT | Update printer config |
| DELETE | `/api/printers/{id}` | JWT | Remove a printer |
| POST | `/api/printers/{id}/test` | JWT | Test connection to a printer |
| POST | `/api/printers/{id}/print` | JWT | Send a print job |
| GET | `/api/printers/discover` | JWT | Discover printers on the network via mDNS/Zeroconf |

---

### Activity Log — `/api/activity-log`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/activity-log/` | JWT | List activity logs. Query: `page`, `limit`, `action`, `entity_type`, `user_name`, `start_date`, `end_date`, `entity_id` |
| GET | `/api/activity-log/entity-types` | JWT | Get distinct entity types for filter dropdown |

---

### Dashboard — `/api/dashboard`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/dashboard/admin` | JWT | Admin KPIs: document counts, user counts, throughput metrics |
| GET | `/api/dashboard/user` | JWT | User-specific KPIs: assigned docs, accuracy, pending reviews |

---

### Migration — `/api/migration`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/migration/documents` | JWT | Migrate legacy documents to the new storage format |

---

### External Share — `/api/external-share`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/external-share` | JWT | Create an external share link for a document |
| GET | `/api/external-share/{token}` | Public | Access a shared document via token (requires password verification) |
| POST | `/api/external-share/{token}/verify` | Public | Verify password for a protected share link |

---

### Health Check

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | Public | Returns `{"status": "ok"}` — used by Docker health checks and load balancers |

---

## Authentication & Authorization Flow

### Standard Login (with 2FA)

```
1.  POST /api/auth/login
    Body: { email, password }
    → Bcrypt verifies password
    → Checks user.status_id == ACTIVE
    → Checks organisation.status_id == ACTIVE
    → Sends OTP to user's email (6-digit, 5-min expiry, purpose=LOGIN)
    ← Returns: { message: "OTP sent" }

2.  POST /api/auth/verify-2fa
    Body: { email, otp }
    → Validates OTP (checks is_used=False, expires_at > now)
    → Marks OTP as used
    → If user has one role → returns access + refresh tokens directly
    → If user has multiple roles → returns { requires_role_selection: true }
    ← Returns: { access_token, refresh_token } OR { requires_role_selection }

3.  POST /api/auth/select-role   (if multiple roles)
    Body: { role_id, organisation_id }
    Headers: Authorization: Bearer <temp_token>
    → Validates user has this role in this organisation
    → Issues full JWT tokens with role_id + organisation_id embedded
    ← Returns: { access_token, refresh_token }
```

### Superadmin Login

```
1.  POST /api/auth/login
    → Detects is_superuser = True
    ← Returns: { temp_token } (short-lived, for org selection only)

2.  POST /api/organisations/select-organisation/{org_id}
    Headers: Authorization: Bearer <temp_token>
    → Issues full token scoped to selected org
    ← Returns: { access_token, refresh_token }
```

### Password Reset

```
1.  POST /api/auth/forgot-password
    Body: { email }
    → Sends OTP to email (purpose=RESET, 10-min expiry)

2.  POST /api/auth/reset-password
    Body: { email, otp, new_password }
    → Validates OTP
    → Hashes new password with bcrypt
    → Updates user.hashed_password
```

### Token Refresh

```
POST /api/auth/refresh
Headers: Authorization: Bearer <refresh_token>
→ Validates refresh token signature and expiry
→ Issues new access token (same role/org claims)
← Returns: { access_token }
```

### JWT Token Structure

**Access Token Payload:**
```json
{
  "sub": "user@example.com",
  "role_id": "uuid-of-role",
  "organisation_id": "uuid-of-org",
  "exp": 1234567890,
  "type": "access",
  "superadmin": false,
  "temp": false
}
```

**Refresh Token Payload:** Same claims, `"type": "refresh"`, expiry = 24 hours.

**Expiry:**
- Access token: 60 minutes
- Refresh token: 24 hours

---

## RBAC — Roles, Modules & Privileges

### Hierarchy

```
Organisation
  └── Role
        ├── Module  ──→  Privilege  (via RoleModule)
        └── Submodule ──→ Privilege (via RoleSubmodule)
```

### Privilege Types

| Privilege | Meaning |
|---|---|
| READ | Can view/list resources |
| CREATE | Can create new resources |
| UPDATE | Can modify existing resources |
| DELETE | Can delete resources |
| MANAGE | Full CRUD over the module |
| ADMIN | Administrative control (includes user management within module) |

### Permission Dependency Injection

```python
# Usage in router
@router.get("/documents")
async def list_documents(
    _: None = Depends(Permission(module="documents", privilege="READ")),
    db: Session = Depends(get_db),
):
    ...
```

The `Permission` class:
1. Extracts `role_id` from the JWT token
2. Queries `RoleModule` joined with `Module` and `Privilege`
3. Checks if the role has the required privilege for the module
4. Also checks `RoleSubmodule` for submodule-level privileges
5. Raises `403 Forbidden` if the privilege is absent
6. Superusers (`is_superuser=True`) bypass all permission checks

---

## Services

### `AuthService` (`app/services/auth_service.py`)
Handles all authentication logic.

| Method | Description |
|---|---|
| `authenticate_user(email, password, db)` | Verify credentials via bcrypt |
| `check_user_active(user, db)` | Validate user + org status are ACTIVE |
| `get_role_permissions(role_id, db)` | Fetch module + submodule privileges for a role |
| `get_user_roles(user_id, db)` | Return all active roles for a user |
| `generate_tokens(user, role_id, org_id)` | Create JWT access + refresh tokens |
| `verify_user_role(user_id, role_id, db)` | Confirm user has the requested role |
| `generate_otp(email, purpose, db)` | Create 6-digit OTP with expiry |
| `verify_otp(email, otp, purpose, db)` | Validate OTP and mark as used |
| `reset_user_password(email, new_password, db)` | Hash and store new password |
| `initiate_2fa(user, db)` | Send OTP email for 2FA verification |

---

### `DocumentService` (`app/services/document_service.py`)
Manages the full document lifecycle.

| Method | Description |
|---|---|
| `upload_documents(files, metadata, db)` | Upload to S3, persist records, trigger AI |
| `get_documents(filters, db)` | Paginated query with filters |
| `get_document(doc_id, db)` | Single document with extracted data |
| `update_document(doc_id, data, db)` | Update metadata |
| `archive_document(doc_id, db)` | Set is_archived = True |
| `delete_document(doc_id, db)` | Remove from DB and S3 |
| `trigger_ai_extraction(doc_id, db)` | Queue AI classification |

---

### `S3Service` (`app/services/s3_service.py`)
Abstracts all AWS S3 interactions.

| Method | Description |
|---|---|
| `upload_file(file, key, bucket, callback)` | Upload with optional progress callback |
| `delete_file(key, bucket)` | Delete an S3 object |
| `download_file(key, bucket)` | Download file bytes |
| `get_file_stream(key, bucket)` | Stream response for large files |
| `generate_presigned_url(key, bucket, expiry)` | Time-limited access URL |

---

### `AISOPService` (`app/services/ai_sop_service.py`)
AI-powered extraction of SOP documents.

| Method | Description |
|---|---|
| `process_sop_document(sop_id, doc_id, db)` | Download doc from S3, extract text, run GPT-4o |
| `extract_text_from_pdf(file_bytes)` | pdfminer.six text extraction |
| `extract_text_from_docx(file_bytes)` | python-docx text extraction |
| `call_openai(prompt, text)` | Azure OpenAI GPT-4o API call |
| `repair_json(raw_str)` | Fallback JSON repair for malformed LLM output |
| `extract_billing_guidelines(data)` | Normalize billing guideline fields |
| `extract_coding_rules(data)` | Normalize CPT/ICD coding rules |

---

### `WebhookService` (`app/services/webhook_service.py`)

| Method | Description |
|---|---|
| `get_user_webhooks(user_id, db)` | List webhooks for user |
| `create_webhook(data, user_id, db)` | Create webhook record |
| `update_webhook(id, data, db)` | Update webhook config |
| `delete_webhook(id, db)` | Delete webhook |
| `dispatch_event(event, payload, db)` | POST payload to all active subscriber URLs |

---

### `ActivityService` (`app/services/activity_service.py`)

| Method | Description |
|---|---|
| `log(action, entity_type, entity_id, details, user_id, org_id, request, db)` | Create ActivityLog record |
| `get_logs(filters, db)` | Paginated log query with filtering |
| `get_entity_types(db)` | Distinct entity_type values |

---

### `UserService` (`app/services/user_service.py`)

| Method | Description |
|---|---|
| `get_users(filters, db)` | Paginated user list with filters |
| `get_user(user_id, db)` | Get user with roles |
| `create_user(data, created_by, db)` | Create user with role assignment |
| `update_user(user_id, data, db)` | Update user fields |
| `activate_user(user_id, db)` | Set status to ACTIVE |
| `deactivate_user(user_id, db)` | Set status to INACTIVE |
| `change_password(user_id, new_password, db)` | Admin password override |
| `map_clients(user_id, client_ids, db)` | Assign clients to user |
| `unmap_clients(user_id, client_ids, db)` | Remove client assignments |
| `get_user_stats(db)` | Return user counts by status |

---

### `FormService` (`app/services/form_service.py`)

| Method | Description |
|---|---|
| `get_forms(page, page_size, status, db)` | Paginated form list |
| `get_form(form_id, db)` | Form with all fields |
| `get_active_form(db)` | Get the active form |
| `get_form_stats(db)` | Count active/inactive forms |
| `create_form(data, user_id, db)` | Create form + fields |
| `update_form(form_id, data, db)` | Update form + replace fields |
| `delete_form(form_id, db)` | Delete form (cascades to fields) |

---

### `ClientService` (`app/services/client_service.py`)

| Method | Description |
|---|---|
| `get_clients(filters, db)` | Paginated client list |
| `get_client(client_id, db)` | Client with locations + providers |
| `create_client(data, created_by, db)` | Create client |
| `update_client(client_id, data, db)` | Update client |
| `soft_delete_client(client_id, db)` | Set deleted_at timestamp |
| `get_client_stats(db)` | Count by status |
| `assign_users(client_id, user_ids, db)` | UserClient mappings |
| `get_locations(client_id, db)` | List client locations |
| `add_location(client_id, data, db)` | Add ClientLocation |
| `get_providers(client_id, db)` | List mapped providers |
| `map_provider(client_id, provider_id, db)` | ProviderClientMapping |
| `npi_lookup(npi)` | External NPI registry HTTP call |
| `import_clients(file, org_id, db)` | Bulk import from Excel/CSV |

---

### `DocumentShareService` (`app/services/document_share_service.py`)

| Method | Description |
|---|---|
| `share_documents(doc_ids, user_ids, shared_by, db)` | Create DocumentShare records |
| `get_shared_with_me(user_id, db)` | Documents shared to current user |
| `get_document_shares(doc_id, db)` | Who a document is shared with |

---

### `ExternalShareService` (`app/services/external_share_service.py`)

| Method | Description |
|---|---|
| `create_share(doc_id, email, password, expires_in, shared_by, db)` | Generate token + hash password |
| `get_share_by_token(token, db)` | Look up share by URL token |
| `verify_password(token, password, db)` | Bcrypt verification |
| `is_expired(share)` | Check expiry timestamp |

---

### `DashboardService` (`app/services/dashboard_service.py`)

| Method | Description |
|---|---|
| `get_admin_stats(org_id, db)` | Document/user/client counts, throughput |
| `get_user_stats(user_id, db)` | Assigned docs, pending, accuracy metrics |

---

### `OrganisationService` (`app/services/organisations_service.py`)

| Method | Description |
|---|---|
| `get_organisations(filters, db)` | Paginated list |
| `get_organisation(org_id, db)` | Single org |
| `get_organisation_stats(db)` | Count by status |
| `create_organisation(data, db)` | Create org |
| `update_organisation(org_id, data, db)` | Update org |
| `activate_organisation(org_id, db)` | Set status ACTIVE |
| `deactivate_organisation(org_id, db)` | Set status INACTIVE |
| `select_organisation(org_id, user, db)` | Superadmin org selection |

---

## Environment Variables

Copy `.env.example` to `.env` before running the app.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string. Format: `postgresql://user:password@host:port/dbname` |
| `DB_SCHEMA` | No | `docucr` | PostgreSQL schema name |
| `JWT_SECRET_KEY` | Yes | — | Secret key for signing JWTs. Generate with `python generate_jwt_secret.py` |
| `FRONTEND_URL` | Yes | `http://localhost:4200` | Allowed CORS origin for frontend |
| `AWS_ACCESS_KEY_ID` | Yes | — | AWS IAM access key for S3 access |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | AWS IAM secret key |
| `AWS_REGION` | Yes | `us-east-1` | AWS region where the S3 bucket is located |
| `AWS_S3_BUCKET` | Yes | — | S3 bucket name for document storage |
| `AZURE_OPENAI_API_KEY` | Yes* | — | Azure OpenAI API key (*required if using Azure) |
| `AZURE_OPENAI_ENDPOINT` | Yes* | — | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes* | `gpt-4o` | Azure OpenAI model deployment name |
| `AZURE_OPENAI_API_VERSION` | Yes* | `2024-12-01-preview` | Azure OpenAI API version |
| `OPENAI_API_KEY` | No | — | OpenAI direct API key (fallback if Azure is not configured) |
| `SMTP_SERVER` | Yes | `smtp.gmail.com` | SMTP mail server hostname |
| `SMTP_PORT` | Yes | `587` | SMTP port (587 for TLS, 465 for SSL) |
| `SMTP_USERNAME` | Yes | — | SMTP login username |
| `SMTP_PASSWORD` | Yes | — | SMTP password or app-specific password |
| `SENDER_EMAIL` | Yes | — | From address used in all outgoing emails |

---

## Local Development Setup

### Prerequisites

**Python:**
```bash
python --version  # 3.10 or higher required
```

**PostgreSQL:**
```bash
# macOS
brew install postgresql
brew services start postgresql

# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
```

**System Libraries (for PDF/image processing):**
```bash
# macOS
brew install poppler tesseract pango libffi

# Ubuntu/Debian
sudo apt install poppler-utils tesseract-ocr libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
```

### Step 1 — Clone and Create Virtual Environment
```bash
git clone <repo-url>
cd docucr-backend

python -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\activate       # Windows PowerShell
```

### Step 2 — Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Configure Environment
```bash
cp .env.example .env
# Edit .env and fill in all required values
```

### Step 4 — Create Database and Schema
```bash
# Connect to PostgreSQL and create DB
psql -U postgres -c "CREATE DATABASE docucr_db;"
psql -U postgres -c "CREATE SCHEMA docucr;" docucr_db
```

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back last migration
alembic downgrade -1

# Generate a new migration (after model changes)
alembic revision --autogenerate -m "description_of_change"

# Show current migration state
alembic current

# Show migration history
alembic history
```

---

## Seeding Initial Data

```bash
# Seeds Roles, Modules, Privileges, Statuses, and default admin user
python run_seed.py

# (Optional) Load master/reference data
python sync_master_data.py
```

---

## Running the Server

```bash
# Using the wrapper script
python app.py

# Using uvicorn directly with hot-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production (no reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at `http://localhost:8000`.

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app tests/

# Run a specific test file
pytest tests/test_auth.py

# Run with verbose output
pytest -v
```

---

## Docker Deployment

### Dockerfile Overview

- **Base image:** `python:3.11-slim`
- **System deps installed:** `gcc`, `poppler-utils`, `libpango`, `libgdk-pixbuf2.0-0`, `libffi-dev`
- **Non-root user:** App runs as `app:app` for security
- **Exposed port:** `8000`
- **Health check:** `GET /api/health` every 30 seconds
- **CMD:** `python -m app.main`

### Build & Run

```bash
# Build Docker image
docker build -t docucr-backend .

# Run with environment file
docker run -p 8000:8000 --env-file .env docucr-backend

# Run with individual env vars
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/docucr_db \
  -e JWT_SECRET_KEY=your-secret \
  -e AWS_S3_BUCKET=your-bucket \
  docucr-backend
```

---

## API Documentation

Once the server is running, interactive API docs are available at:

| Interface | URL |
|---|---|
| Swagger UI (interactive) | http://localhost:8000/docs |
| ReDoc (read-only) | http://localhost:8000/redoc |
| OpenAPI JSON schema | http://localhost:8000/openapi.json |

---

## Security

- All endpoints except `/api/auth/*`, `/api/health`, and `/api/external-share/{token}` require a valid JWT in the `Authorization: Bearer` header.
- RBAC is enforced per-route via the `Permission` dependency — a 403 is returned if the user's role lacks the required privilege.
- Passwords are stored as bcrypt hashes (never plaintext).
- OTPs are single-use and expire after a configurable time window.
- External share links use password-protected bcrypt hashes + expiry timestamps.
- CORS is restricted to `FRONTEND_URL` (configurable in environment).
- The Docker container runs as a non-root user (`app:app`).

---

© 2025 docucr Platform. All Rights Reserved.
