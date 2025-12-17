RouteHub REST API
=================

This project implements the OpenAPI Description for the RouteHub system.


Requirements
------------

* python == 3.12
* rust == 1.89.0 (required to compile `pydantic_core`)
* binutils == 2.44 (required to compile `uvloop`)


Initial Setup
-------------

Create the virtual environment.

```bash
python -m venv .venv --prompt "rh"
```

Activate the virtual environment.

```bash
source .venv/bin/activate
```

Upgrade `pip` package manager.

```bash
python -m pip install --upgrade pip
```

Install python dependencies from `requirements.txt` file.

```bash
pip install -r requirements.txt
```

Exit from the virtual environment.

```bash
deactivate
```


Run REST API server
-------------------

Activate the virtual environment if you haven't already.

```bash
source .venv/bin/activate
```

Start the "development" HTTP server with the command below this paragraph. Use the `ENVIRONMENT` environment variable to specify if you are starting the server locally (`LCL`) or in production (`PRD`). The `RDBMS_URL` environment variable configures the relational database management system.

```bash
ENVIRONMENT=LCL \
RDBMS_URL=sqlite:///sqlite/routehub.db \
fastapi dev main.py
```

By default, the server start at [http://127.0.0.1:8000](http://127.0.0.1:8000). You can check it in the output from the previous command.

We can change the host and port using the `--port` and `--host` parameters, as shown in the next command.

```bash
ENVIRONMENT=LCL \
RDBMS_URL=sqlite:///sqlite/routehub.db \
fastapi dev --host 0.0.0.0 --port 3000 main.py
```
