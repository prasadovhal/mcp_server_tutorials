"""

POST Request (Create Data)

"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class User(BaseModel):
    name: str
    age: int

@app.post("/users")
def create_user(user:User):
    return {"message":"User created", "data":user}

"""
created data is not stored directly, if we have to save this data we have make those provision ourselves, such as json, csv, sqlite etc.
"""
