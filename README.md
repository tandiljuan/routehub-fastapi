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

Start the "development" HTTP server.

```bash
fastapi dev main.py
```

By default, the server start at [http://127.0.0.1:8000](http://127.0.0.1:8000). You can check it in the output from the previous command.

We can change the port using the `--port` parameter, as shown in the next command.

```bash
fastapi dev --port 3000 main.py
```
