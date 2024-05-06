# Utilisez une image de base Python officielle
FROM python:3.9-slim

# Définissez le répertoire de travail
WORKDIR /app


# Installer les dépendances Python
COPY ./requirements.txt /app/requirements.txt

# Installez les dépendances de l'application
RUN pip install --no-cache-dir -r requirements.txt

# Copiez votre application Flask et les fichiers de modèle dans le conteneur
COPY . /app/

# Exposez le port utilisé par votre application
EXPOSE 5000

# Commande pour lancer l'application
CMD ["flask", "run", "--host=0.0.0.0"]
