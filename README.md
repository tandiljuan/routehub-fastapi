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

Create the virtual environment

```bash
python -m venv .venv --prompt "rh"
```

Activate the virtual environment

```bash
source .venv/bin/activate
```

Upgrade `pip` package manager

```bash
python -m pip install --upgrade pip
```

Install python dependencies from `requirements.txt` file

```bash
pip install -r requirements.txt
```
