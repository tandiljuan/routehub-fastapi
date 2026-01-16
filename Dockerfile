FROM python:3.12-alpine AS setup
LABEL stage=rh-setup

RUN echo ">>> Starting Alpine packages installation..." \
    && apk update \
    && apk add --no-cache \
       postgresql-dev \
       build-base \
    && echo ">>> Alpine packages installation completed."

COPY requirements.txt .

RUN echo ">>> Starting Python packages installation..." \
    && pip install \
       --no-cache-dir \
       --no-warn-script-location \
       --user \
       --root-user-action ignore \
       --requirement requirements.txt \
    && echo ">>> Python packages installation completed."

# --------------------------------------

FROM python:3.12-alpine AS runtime
LABEL stage=rh-runtime

RUN echo ">>> Starting Alpine packages installation..." \
    && apk update \
    && apk add --no-cache \
       postgresql-libs \
    && rm -rf /var/cache/apk/* \
    && echo ">>> Alpine packages installation completed."

WORKDIR /service

COPY --from=setup /root/.local /root/.local

# Make sure scripts in .local are usable:
ENV PATH=/root/.local/bin:$PATH

ENV UVICORN_HOST="0.0.0.0"
ENV UVICORN_PORT="80"
ENV UVICORN_SERVER_HEADER=false
ENV UVICORN_TIMEOUT_KEEP_ALIVE=10
ENV UVICORN_LOG_LEVEL=info

COPY . /service

CMD ["uvicorn", "main:app"]
