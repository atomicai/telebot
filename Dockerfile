FROM python:3.11-slim

WORKDIR /opt/app-root/src/

COPY requirements.txt /opt/app-root/requirements.txt

RUN pip install --no-cache-dir -r /opt/app-root/requirements.txt

ENV PYTHONPATH /opt/app-root/src
ENV PYTHONUNBUFFERED=1

COPY entrypoint.sh /opt/app-root
RUN chmod +x /opt/app-root/entrypoint.sh

CMD ["/opt/app-root/entrypoint.sh"]