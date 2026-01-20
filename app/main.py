from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
<<<<<<< HEAD
from .routers import auth_router, modules_router, roles_router, privileges_router, users_router, statuses_router, profile_router, forms_router, clients_router, document_types_router, templates_router, documents_router, document_list_config_router, document_share_router, dashboard_router, webhook_router, external_share_router, migration_router, test_router, document_ai_router
=======
from .routers import auth_router, modules_router, roles_router, privileges_router, users_router, statuses_router, profile_router, forms_router, clients_router, document_types_router, templates_router, documents_router, document_list_config_router, document_share_router, dashboard_router, webhook_router, external_share_router, migration_router, test_router, printers_router
>>>>>>> d5260f51450535dfe5f5c9b3fc3170e3ab6d1925
# Import all models to ensure they are registered with Base metadata
from .models import user, role, privilege, status, module, document, template, extracted_document, unverified_document, document_list_config, document_share, webhook, external_share, printer

app = FastAPI(title="docucr API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(modules_router.router, prefix="/api/modules", tags=["modules"])
app.include_router(document_ai_router.router, prefix="/api/ai", tags=["AI"])
app.include_router(roles_router.router, prefix="/api/roles", tags=["roles"])
app.include_router(privileges_router.router, prefix="/api/privileges", tags=["privileges"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])
app.include_router(statuses_router.router, prefix="/api/statuses", tags=["statuses"])
app.include_router(profile_router.router, prefix="/api/profile", tags=["profile"])
app.include_router(forms_router.router, prefix="/api/forms", tags=["forms"])
app.include_router(clients_router.router, prefix="/api/clients", tags=["clients"])
app.include_router(document_types_router.router)
app.include_router(templates_router.router)
app.include_router(documents_router.router)
app.include_router(document_list_config_router.router)
app.include_router(document_share_router.router)
app.include_router(dashboard_router.router)
app.include_router(webhook_router.router)
app.include_router(external_share_router.router)
app.include_router(migration_router.router)
app.include_router(external_share_router.router)
app.include_router(migration_router.router)
app.include_router(test_router.router)
app.include_router(printers_router.router, prefix="/api/printers", tags=["printers"])

@app.get("/")
async def root():
    return {"message": "docucr API is running"}

@app.get("/health")
async def health_simple():
    return {"status": "ok"}

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True, forwarded_allow_ips="*")