import os
import sys
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Text, ForeignKey, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func
from passlib.context import CryptContext
from dotenv import load_dotenv
import uuid

load_dotenv()

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

def get_password_hash(password):
    return pwd_context.hash(password)

# Create database session
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_super_admin():
    # Create schema and tables
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
        conn.commit()
    print("✓ Schema verified")
    
    Base.metadata.create_all(bind=engine)
    print("✓ Tables verified")
    
    db = SessionLocal()
    try:
        # Create SUPER_ADMIN role
        role = db.query(Role).filter(Role.name == "SUPER_ADMIN").first()
        if not role:
            role = Role(
                id=str(uuid.uuid4()),
                name="SUPER_ADMIN",
                description="Super Administrator with full access",
                is_active=True
            )
            db.add(role)
            db.commit()
            print("✓ SUPER_ADMIN role created")
        else:
            print("✓ SUPER_ADMIN role already exists")
        
        # Create user
        user = db.query(User).filter(User.email == "suman.singh@marvelsync.com").first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email="suman.singh@marvelsync.com",
                username="mrvamp",
                hashed_password=get_password_hash("Suman@Admin22"),
                first_name="Suman",
                last_name="Singh",
                is_active=True,
                is_superuser=True
            )
            db.add(user)
            db.commit()
            print("✓ User created: suman.singh@marvelsync.com")
        else:
            print("✓ User already exists: suman.singh@marvelsync.com")
        
        # Assign role to user
        user_role = db.query(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id
        ).first()
        if not user_role:
            user_role = UserRole(
                id=str(uuid.uuid4()),
                user_id=user.id,
                role_id=role.id
            )
            db.add(user_role)
            db.commit()
            print("✓ SUPER_ADMIN role assigned to user")
        else:
            print("✓ Role already assigned")
        
        print("\n✅ Setup complete!")
        print(f"Email: suman.singh@marvelsync.com")
        print(f"Password: Suman@Admin22")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_super_admin()
