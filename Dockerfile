# The agent writes and runs its own code. Run it here, not on your machine.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 stem

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stem ./stem
COPY tests ./tests
COPY pytest.ini ./

USER stem
ENTRYPOINT ["python", "-m", "stem"]
CMD ["--help"]
