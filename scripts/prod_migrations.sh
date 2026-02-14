#!/bin/bash

echo "> Running migrations"
poetry run flask db upgrade
