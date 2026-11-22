FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# URL da API embutido no bundle na construção (ex.: --build-arg VITE_API_BASE=https://rag-api.exemplo.cv).
# Vazio: http://127.0.0.1:8000 (ver src/api.js).
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# nginx:1.27-alpine (Alpine 3.21) tinha openssl, curl, expat, libpng e brotli vulneráveis.
FROM nginx:1.30-alpine
RUN apk upgrade --no-cache
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
