# syntax=docker/dockerfile:1

# --- Étape 1 : build de l'application ---
ARG NODE_BUILD_IMAGE=node:24-alpine
ARG NGINX_RUNTIME_IMAGE=nginx:1.30-alpine
FROM ${NODE_BUILD_IMAGE} AS build
WORKDIR /app
# Certificats CA d'entreprise (proxy à inspection TLS) pour npm.
# Hors proxy le dossier peut ne contenir que .gitkeep.
COPY certs/ /certs/
RUN touch /certs/ca-bundle.crt
ENV NODE_EXTRA_CA_CERTS=/certs/ca-bundle.crt
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- Étape 2 : service statique via Nginx ---
FROM ${NGINX_RUNTIME_IMAGE} AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
