FROM python:3.11-slim

WORKDIR /opt/app-root/src/

COPY requirements.txt /opt/app-root/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH /opt/app-root/src
ENV PYTHONUNBUFFERED=1

COPY src/llm_bot/entrypoint.sh /opt/app-root/src/llm_bot/
RUN chmod +x /opt/app-root/src/llm_bot/entrypoint.sh

CMD ["/opt/app-root/src/llm_bot/entrypoint.sh"]