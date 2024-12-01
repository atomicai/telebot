#!/bin/sh

exec gunicorn --config /opt/app-root/src/llm_bot/api/config/gunicorn.conf.py
