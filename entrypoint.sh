#!/bin/sh

if [ "$TELEGRAM_BOT_MODE" = "webhook" ]; then
    exec gunicorn --config /opt/app-root/src/llm_bot/api/config/gunicorn.conf.py
else
    echo "Invalid TELEGRAM_BOT_MODE. Use 'webhook' or 'polling'."
    exit 1
fi
