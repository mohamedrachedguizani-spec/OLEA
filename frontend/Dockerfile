FROM node:18-alpine

WORKDIR /app

# Copier le package.json et installer les dépendances
COPY package.json ./
RUN npm install

# Copier le reste des fichiers du frontend et compiler le projet
COPY . .
RUN npm run build

# Installer le serveur de fichiers statiques Node.js léger
RUN npm install -g serve

# Exposer le port de l'application
EXPOSE 3000

# Lancer la distribution de production sur le port 3000
CMD ["serve", "-s", "build", "-l", "3000"]
