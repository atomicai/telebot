#!/bin/sh

exec gunicorn -c /opt/app-root/src/api/config/gunicorn.conf.py api.application:app

