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
* `BEARER_TOKEN`: The Bearer token required to authorize API usage.
* `RDBMS_URL`: Configures the relational database management system.
* `OPTIMIZER_HOST`: Sets the optimizer service host.
* `OPTIMIZER_PORT`: Sets the optimizer service port.
* `OPTIMIZER_AUTH`: Sets the optimizer service authentication passkey.

Next, is an example of the command to start the development server.

```bash
ENVIRONMENT=LCL \
BEARER_TOKEN=1234 \
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
BEARER_TOKEN=1234 \
RDBMS_URL=sqlite:///sqlite/routehub.db \
OPTIMIZER_HOST=http://localhost \
OPTIMIZER_PORT=3005 \
OPTIMIZER_AUTH=example \
fastapi dev --host 0.0.0.0 --port 3000 main.py
```


Docker
------

Containers can be used to create a reproducible and isolated environment in which to run the REST API server. The `Dockerfile` and `.dockerignore` files detail the steps required to create the image. We will use [Docker](https://github.com/docker) to build the image with the following command:

```bash
docker build --tag 'routehub/api' .
```

Once the build process finishes, run the command below to remove any intermediate images.

```bash
docker image prune --force --filter label=stage=rh-setup
```

At this point the image is ready for use. However, the REST API requires a database. For a local development environment, an SQLite database can be used. Check the [dbschem](https://github.com/tandiljuan/routehub-dbschem) project for instructions on how to create and set up the database.

Assuming the database is located at `/path/to/sqlite.db`, the following command will run the container and expose the service on port `8000`.

```bash
docker run --rm -it \
  --name "routehub-api" \
  --volume "/path/to/sqlite.db:/opt/routehub.db" \
  --env ENVIRONMENT=LCL \
  --env RDBMS_URL="sqlite:////opt/routehub.db" \
  --env OPTIMIZER_HOST="http://localhost" \
  --env OPTIMIZER_PORT=3005 \
  --env OPTIMIZER_AUTH=example \
  --publish 8000:80 \
  routehub/api
```

You can check the automatically generated OpenAPI documentation page by navigating to [http://localhost:8000/docs](http://localhost:8000/docs) and test the service from there.

### Compose

In the previous section, we learned how to create and run the REST API container image. Here, we will demonstrate how to run the REST API in a multi-container environment where the application runs in one container and, for example, the database runs in a separate container. To accomplish this, we will use [Docker Compose](https://github.com/docker/compose), with the key files being `docker-compose.env.example` and `docker-compose.yaml`.

Before starting the application, you need to create the `docker-compose.env` file. Let's use the example one, and then you can update it as needed.

```bash
cp docker-compose.env.example docker-compose.env
```

Then, you can boot the containers using the [`up`](https://docs.docker.com/reference/cli/docker/compose/up/) command.

```bash
docker compose up -d
```

However, if you want `docker compose` to also inherit environment variables defined in `docker-compose.env` (e.g., for variable substitution within `docker-compose.yaml`), you can run the following command instead. The [`set -a`](https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html) command (equivalent to `-o allexport`) exports all variables to the environment for subsequent commands.

```bash
(set -a; source ./docker-compose.env; set +a; docker compose up -d)
```

The previous command runs the containers in detached mode. To check the output, you can use the [`logs`](https://docs.docker.com/reference/cli/docker/compose/logs/) command.

```bash
docker compose logs --no-color | less
```

Once you finish working with the service, you can [`stop`](https://docs.docker.com/reference/cli/docker/compose/stop/) the containers if you plan to restart them later, or you can use the [`down`](https://docs.docker.com/reference/cli/docker/compose/down/) command to remove them and all associated resources.

```bash
docker compose down [--rmi local|all] [--volumes]
```
