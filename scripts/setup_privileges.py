import os
import sys
from sqlalchemy import create_engine, text, Column, String, Boolean, Text, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func
from dotenv import load_dotenv
import uuid

load_dotenv()

Base = declarative_base()

# Define models inline
class User(Base):
    __tablename__ = "user"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_client = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Role(Base):
    __tablename__ = "role"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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

class Privilege(Base):
    __tablename__ = "privilege"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class RoleModule(Base):
    __tablename__ = "role_module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    module_id = Column(String, ForeignKey('docucr.module.id'), nullable=False)
    privilege_id = Column(String, ForeignKey('docucr.privilege.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserRoleModule(Base):
    __tablename__ = "user_role_module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    role_module_id = Column(String, ForeignKey('docucr.role_module.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_privileges_and_permissions():
    # Create schema and tables
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
        conn.commit()
    
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Create Privileges
        privileges_data = [
            {"name": "CREATE", "description": "Create new records"},
            {"name": "READ", "description": "View and read records"},
            {"name": "UPDATE", "description": "Edit and update records"},
            {"name": "DELETE", "description": "Delete records"},
            {"name": "EXPORT", "description": "Export data"},
            {"name": "IMPORT", "description": "Import data"},
            {"name": "APPROVE", "description": "Approve workflows"},
            {"name": "MANAGE", "description": "Full management access"}
        ]
        
        created_privileges = {}
        for priv_data in privileges_data:
            existing = db.query(Privilege).filter(Privilege.name == priv_data["name"]).first()
            if not existing:
                privilege = Privilege(
                    id=str(uuid.uuid4()),
                    **priv_data
                )
                db.add(privilege)
                created_privileges[priv_data["name"]] = privilege
                print(f"✓ Created privilege: {priv_data['name']}")
            else:
                created_privileges[priv_data["name"]] = existing
                print(f"✓ Privilege already exists: {priv_data['name']}")
        
        db.commit()
        
        # 2. Get SUPER_ADMIN role and user
        super_admin_role = db.query(Role).filter(Role.name == "SUPER_ADMIN").first()
        if not super_admin_role:
            print("❌ SUPER_ADMIN role not found!")
            return
        
        user = db.query(User).filter(User.email == "suman.singh@marvelsync.com").first()
        if not user:
            print("❌ User suman.singh@marvelsync.com not found!")
            return
        
        # 3. Get all modules
        modules = db.query(Module).all()
        
        # 4. Assign all privileges for all modules to SUPER_ADMIN role
        for module in modules:
            for privilege_name, privilege in created_privileges.items():
                # Check if role_module already exists
                existing_role_module = db.query(RoleModule).filter(
                    RoleModule.role_id == super_admin_role.id,
                    RoleModule.module_id == module.id,
                    RoleModule.privilege_id == privilege.id
                ).first()
                
                if not existing_role_module:
                    role_module = RoleModule(
                        id=str(uuid.uuid4()),
                        role_id=super_admin_role.id,
                        module_id=module.id,
                        privilege_id=privilege.id
                    )
                    db.add(role_module)
                    
                    # Assign to user
                    user_role_module = UserRoleModule(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        role_module_id=role_module.id
                    )
                    db.add(user_role_module)
                    
                    print(f"✓ Assigned {privilege_name} privilege for {module.label} to SUPER_ADMIN")
        
        db.commit()
        
        print(f"\n✅ Setup complete!")
        print(f"✓ Created {len(privileges_data)} privileges")
        print(f"✓ Assigned all privileges for {len(modules)} modules to SUPER_ADMIN role")
        print(f"✓ Granted full access to user: suman.singh@marvelsync.com")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    setup_privileges_and_permissions()