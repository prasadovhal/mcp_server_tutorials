"""

Query Parameters
example: /search?q=python

"""

from fastapi import FastAPI

app = FastAPI()

@app.get("/search")
def search(q:str):
    return {"query":q}