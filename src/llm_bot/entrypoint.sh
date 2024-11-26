#!/bin/sh

if [ "$TELEGRAM_BOT_MODE" = "webhook" ]; then
    exec gunicorn --config /opt/app-root/src/llm_bot/api/config/gunicorn.conf.py
elif [ "$TELEGRAM_BOT_MODE" = "polling" ]; then
    exec python /opt/app-root/src/llm_bot/api/main.py
else
    echo "Invalid TELEGRAM_BOT_MODE. Use 'webhook' or 'polling'."
    exit 1
fi
