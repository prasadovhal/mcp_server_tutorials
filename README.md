# mcp_server_tutorials
How to create API and MCP servers tutorials from basic to advance


## Set up Python & Poetry

1. cd mcp_server_tutorials
2. install poetry
`(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -`
3. run `C:\Users\user_name\AppData\Roaming\Python\Scripts`
4. check poetry version `poetry --version`
5. set `poetry config virtualenvs.in-project true`
6. run `poetry install`
7. set venv 
   - for windows `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` or `.venv\Scripts\activate`
   - for linux/mac `source .venv/bin/activate`
