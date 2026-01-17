from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth_router, modules_router, roles_router, privileges_router, users_router, statuses_router, profile_router, forms_router, clients_router

app = FastAPI(title="DocuCR API", version="1.0.0")

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
app.include_router(roles_router.router, prefix="/api/roles", tags=["roles"])
app.include_router(privileges_router.router, prefix="/api/privileges", tags=["privileges"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])
app.include_router(statuses_router.router, prefix="/api/statuses", tags=["statuses"])
app.include_router(profile_router.router, prefix="/api/profile", tags=["profile"])
app.include_router(forms_router.router, prefix="/api/forms", tags=["forms"])
app.include_router(clients_router.router, prefix="/api/clients", tags=["clients"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)