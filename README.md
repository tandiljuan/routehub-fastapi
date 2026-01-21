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

Now you can start the "development" HTTP server. Below is a list of environment variables accepted by the application.

* `ENVIRONMENT`: Specify if you are starting the server locally (`LCL`) or in production (`PRD`).
* `RDBMS_URL`: Configures the relational database management system.
* `OPTIMIZER_HOST`: Sets the optimizer service host.
* `OPTIMIZER_PORT`: Sets the optimizer service port.
* `OPTIMIZER_AUTH`: Sets the optimizer service authentication passkey.

Next, is an example of the command to start the development server.

```bash
ENVIRONMENT=LCL \
RDBMS_URL=sqlite:///sqlite/routehub.db \
OPTIMIZER_HOST=http://localhost \
OPTIMIZER_PORT=3005 \
OPTIMIZER_AUTH=example \
fastapi dev main.py
```

By default, the server start at [http://127.0.0.1:8000](http://127.0.0.1:8000). You can check it in the output from the previous command.

We can change the host and port using the `--port` and `--host` parameters, as shown in the next command.

```bash
ENVIRONMENT=LCL \
RDBMS_URL=sqlite:///sqlite/routehub.db \
OPTIMIZER_HOST=http://localhost \
OPTIMIZER_PORT=3005 \
OPTIMIZER_AUTH=example \
fastapi dev --host 0.0.0.0 --port 3000 main.py
```
