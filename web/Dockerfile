# HX-Email frontend (Vite build -> nginx)
FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine

COPY --from=build /app/dist /usr/share/nginx/html
# Rendered by the official image's envsubst entrypoint on startup
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV LISTEN_PORT=8080 \
    API_TARGET=http://127.0.0.1:18090

EXPOSE 8080
