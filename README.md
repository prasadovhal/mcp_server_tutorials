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


## API vs MCP server

| Feature          | Traditional API                                | MCP Server                                        |
| ---------------- | ---------------------------------------------- | ------------------------------------------------- |
| Primary Audience | Human developers writing code                  | AI models / LLM agents                            |
| Integration      | Requires custom code for every single service  | "Build once| works with any MCP-compatible AI"    |
| Discovery        | Manual (reading docs)                          | Automatic (runtime capability negotiation)        |
| Structure        | "Endpoints (REST, GraphQL, SOAP)"              | "Tools| Resources| and Prompts"                   |
| Adaptability     | Rigid; breaks if the endpoint changes          | Flexible; AI adapts to available tools on the fly |