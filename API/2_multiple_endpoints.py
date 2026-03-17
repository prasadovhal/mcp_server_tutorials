"""

Creating Multiple Endpoints

"""


from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def get_users():
    return ["Prasad","Rahul","Anita"]

@app.get("/users/{user_id}")
def get_user(user_id:int):
    return {"user_id":user_id}