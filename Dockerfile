FROM python:3.13-alpine

ARG APP_UID=1000
ARG APP_GID=1000
RUN apk add --no-cache ffmpeg \
    && addgroup -g "${APP_GID}" -S app && adduser -u "${APP_UID}" -S -D -H -G app app

WORKDIR /app
COPY --chown=app:app *.py requirements.txt /app/

USER app:app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/app/bot.py"]
