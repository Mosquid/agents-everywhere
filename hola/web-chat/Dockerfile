FROM node:22-alpine AS sdk
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html ./
COPY --from=sdk /build/node_modules/livekit-client/dist/livekit-client.umd.js ./sdk.js
CMD ["python", "server.py"]
