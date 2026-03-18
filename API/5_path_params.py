"""
Think of path parameters like a house address:
    City → Street → House Number

API equivalent:
    /users/10
"""


from fastapi import FastAPI

app = FastAPI()

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {
        "message": f"User ID is {user_id}"
    }