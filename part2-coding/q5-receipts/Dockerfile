# the receipt reader as a container image.
#
# slim and not alpine: psycopg2-binary and Pillow both ship ready built wheels
# for debian, and on alpine (musl) pip has to compile them from source instead,
# which needs a compiler in the image and turns a 20 second build into minutes.

FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: no .pyc files, nothing writes them back into a
#   layer that is meant to be read only.
# PYTHONUNBUFFERED: print() reaches "docker logs" straight away instead of
#   sitting in a buffer until the process exits.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements first, on its own. this layer is cached and only rebuilds when
# the file changes, so editing python code does not reinstall django every time.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

# root inside a container is still root on the host if anything escapes, and
# nothing here needs to write to the filesystem.
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 8000

# entrypoint waits for postgres and migrates, then hands over to whatever CMD
# is. keeping them separate means "docker run <image> python manage.py shell"
# still gets the waiting and the migrations for free.
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
