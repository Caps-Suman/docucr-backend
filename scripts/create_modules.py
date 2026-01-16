import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import uuid

load_dotenv()

# Import models inline to avoid conflicts
from sqlalchemy import Column, String, Boolean, Text, Integer, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Module(Base):
    __tablename__ = "module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    route = Column(String, nullable=False)
    icon = Column(String, nullable=True)
    category = Column(String, nullable=False)
    has_submodules = Column(Boolean, default=False)
    submodules = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    color_from = Column(String, nullable=True)
    color_to = Column(String, nullable=True)
    color_shadow = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_modules():
    # Create schema and tables
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
        conn.commit()
    
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        modules_data = [
            {
                "name": "dashboard",
                "label": "Dashboard",
                "description": "Main dashboard with overview and analytics",
                "route": "/dashboard",
                "icon": "LayoutDashboard",
                "category": "main",
                "display_order": 1,
                "color_from": "#667eea",
                "color_to": "#764ba2"
            },
            {
                "name": "documents",
                "label": "Documents",
                "description": "Document management and processing",
                "route": "/documents",
                "icon": "FileText",
                "category": "main",
                "display_order": 2,
                "color_from": "#f093fb",
                "color_to": "#f5576c"
            },
            {
                "name": "templates",
                "label": "Templates",
                "description": "Document templates and forms",
                "route": "/templates",
                "icon": "Layout",
                "category": "main",
                "display_order": 3,
                "color_from": "#4facfe",
                "color_to": "#00f2fe"
            },
            {
                "name": "sops",
                "label": "SOPs",
                "description": "Standard Operating Procedures",
                "route": "/sops",
                "icon": "BookOpen",
                "category": "main",
                "display_order": 4,
                "color_from": "#43e97b",
                "color_to": "#38f9d7"
            },
            {
                "name": "clients",
                "label": "Clients",
                "description": "Client management and information",
                "route": "/clients",
                "icon": "Users",
                "category": "main",
                "display_order": 5,
                "color_from": "#fa709a",
                "color_to": "#fee140"
            },
            {
                "name": "users_permissions",
                "label": "User & Permissions",
                "description": "User management and access control",
                "route": "/users-permissions",
                "icon": "Shield",
                "category": "admin",
                "display_order": 6,
                "color_from": "#a8edea",
                "color_to": "#fed6e3"
            },
            {
                "name": "settings",
                "label": "Settings",
                "description": "System configuration and preferences",
                "route": "/settings",
                "icon": "Settings",
                "category": "admin",
                "display_order": 7,
                "color_from": "#d299c2",
                "color_to": "#fef9d7"
            },
            {
                "name": "profile",
                "label": "Profile",
                "description": "User profile and account settings",
                "route": "/profile",
                "icon": "User",
                "category": "user",
                "display_order": 8,
                "color_from": "#89f7fe",
                "color_to": "#66a6ff"
            }
        ]
        
        for module_data in modules_data:
            existing = db.query(Module).filter(Module.name == module_data["name"]).first()
            if not existing:
                module = Module(
                    id=str(uuid.uuid4()),
                    **module_data
                )
                db.add(module)
                print(f"✓ Created module: {module_data['label']}")
            else:
                print(f"✓ Module already exists: {module_data['label']}")
        
        db.commit()
        print("\n✅ All modules created successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_modules()