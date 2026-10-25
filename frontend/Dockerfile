# syntax=docker/dockerfile:1

# --- Étape 1 : build de l'application ---
FROM node:20-alpine AS build
WORKDIR /app
# Certificats CA d'entreprise (proxy à inspection TLS) pour npm.
# Hors proxy le dossier peut ne contenir que .gitkeep.
COPY certs/ /certs/
RUN touch /certs/ca-bundle.crt
ENV NODE_EXTRA_CA_CERTS=/certs/ca-bundle.crt
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# --- Étape 2 : service statique via Nginx ---
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
