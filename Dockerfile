FROM python:3.12-slim
WORKDIR /app
COPY mountain_editor /app/mountain_editor
COPY editorial.md /app/editorial.md
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/editor.db
CMD ["python", "-m", "mountain_editor", "run"]
