FROM node:24-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir python-jobspy pandas
COPY scraper.py ./
COPY --from=web /web/dist ./public
CMD ["python", "-u", "scraper.py"]
