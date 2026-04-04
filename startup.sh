#!/bin/bash
set -e
 
echo "Running database migrations..."
python manage.py migrate --noinput
 
echo "Starting gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 60 main.wsgi:application