#!/usr/bin/env bash

docker run --rm -t -p 127.0.0.1:5432:5432 \
    -e POSTGRES_USER=hushline \
    -e POSTGRES_PASSWORD=hushline \
    -e POSTGRES_DB=hushline \
    postgres:16.4-alpine3.20
