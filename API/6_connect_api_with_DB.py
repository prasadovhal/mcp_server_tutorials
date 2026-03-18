from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

# DB setup
engine = create_engine("sqlite:///./test.db")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Table
class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    age = Column(Integer)

Base.metadata.create_all(bind=engine)

# API
app = FastAPI()

# Request schema
class User(BaseModel):
    name: str
    age: int

# CREATE user
@app.post("/users")
def create_user(user: User):
    db = SessionLocal()

    new_user = UserDB(name=user.name, age=user.age)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

# READ users
@app.get("/users")
def get_users():
    db = SessionLocal()
    users = db.query(UserDB).all()
    return users