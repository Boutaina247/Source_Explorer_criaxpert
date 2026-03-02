# 🔍 Creaformation — Source Explorer

> **Outil interne de l'équipe Creaformation** — Pipeline automatisé de recherche, validation et extraction de sources pédagogiques sur l'IA.

---

## C'est quoi cet outil ?

Source Explorer est une application web interne qui permet à l'équipe de **trouver de vraies sources fiables** sur un sujet IA, de **vérifier leur qualité automatiquement**, et de **générer un brouillon de module de formation** en quelques clics.

### Ce que fait l'outil, étape par étape

```
1. Tu tapes un sujet (ex: "IA générative et RGPD")
        ↓
2. Tavily cherche de vraies sources sur le web (articles, rapports, études)
        ↓
3. Chaque source reçoit un score de qualité automatique (0-100)
   → Domaine de confiance (Stanford, CNIL, arXiv...)
   → Fraîcheur (2024 > 2023 > 2022...)
   → Richesse du contenu
        ↓
4. Claude (IA) lit le contenu réel des sources validées
   et extrait les concepts clés, points pédagogiques, idées quiz
        ↓
5. Un brouillon de module complet est généré
   (objectifs, plan de cours, quiz, exercice)
        ↓
6. Tu exportes tout en .txt pour le garder ou le partager
```

> ⚠️ **Important** : Claude ne génère JAMAIS les sources lui-même. Les sources viennent toujours d'une vraie recherche web (Tavily) ou de tes propres URLs.

---

## Architecture technique

```
GitHub (code source)
    ↓
Vercel (héberge le frontend — interface web)
    ↓ appels API
Railway (héberge le backend — serveur Python FastAPI)
    ↓ recherche web          ↓ extraction IA
Tavily API               Anthropic API (Claude)
```

---

## Pour l'équipe — Comment utiliser l'app

### 1. Accéder à l'app

Ouvre ce lien dans ton navigateur :
**`https://source-explorer-criaxpert.vercel.app`**

### 2. Configuration (première fois uniquement)

Clique sur **⚙️ Configuration** en haut à droite et remplis :

| Champ | Valeur |
|-------|--------|
| URL du backend | `https://sourceexplorercriaxpert-production.up.railway.app` |
| Secret interne | *(demande à Boutaina)* |

Clique **💾 Sauvegarder**. Cette configuration est sauvegardée dans ton navigateur — tu n'auras plus à la refaire.

### 3. Lancer une recherche

**Mode automatique 🔍** *(recommandé)*
- Clique sur une suggestion Bloc 1, ou tape ton propre sujet
- Clique **🚀 Lancer**
- Attends 20-40 secondes

**Mode manuel 📎** *(si tu as déjà des sources — ex: depuis NotebookLM)*
- Clique sur l'onglet **"📎 Ajouter mes sources manuellement"**
- Colle les URLs une par une
- Tape le sujet du module dans le champ en bas
- Clique **🚀 Analyser**

### 4. Lire les résultats

L'app affiche 3 onglets :

**📚 Sources**
- Liste toutes les sources trouvées avec leur score de qualité
- Couleur verte = excellente source (≥85/100)
- Couleur orange = bonne source (70-84/100)
- Couleur rouge = à vérifier (<70/100)
- Clique sur une source pour voir le détail (scores par dimension, description)

**🧪 Contenu extrait**
- Angle pédagogique recommandé
- Concepts clés avec définitions
- Points pédagogiques pour le cours
- Idées de questions quiz
- Idées d'exercices

**✏️ Brouillon module**
- Titre et description catalogue
- Objectifs d'apprentissage
- Plan de cours avec durées
- Questions quiz avec réponses et explications
- Exercice principal avec étapes

### 5. Exporter

Clique **⬇️ Exporter .txt** pour télécharger un fichier texte complet avec toutes les sources, le contenu extrait et le brouillon.

---

## Pour les développeurs — Structure du projet

```
Source_Explorer_criaxpert/
├── frontend/
│   └── index.html          # App web complète (HTML/CSS/JS)
├── backend/
│   ├── main.py             # Serveur FastAPI (Python)
│   ├── requirements.txt    # Dépendances Python
│   ├── Procfile            # Commande de démarrage Railway
│   ├── .python-version     # Force Python 3.11
│   └── .env.example        # Template variables d'environnement
├── .gitignore
└── README.md
```

### Variables d'environnement (Railway)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Clé API Anthropic (Claude) |
| `TAVILY_API_KEY` | Clé API Tavily (recherche web) |
| `TOOL_SECRET` | Secret partagé entre frontend et backend |
| `PORT` | Port d'écoute (8080) |

### Routes API backend

| Route | Méthode | Description |
|-------|---------|-------------|
| `/` | GET | Health check |
| `/api/health` | GET | Vérifie les clés API |
| `/api/search` | POST | Recherche Tavily + scoring qualité |
| `/api/fetch-urls` | POST | Extrait le contenu d'URLs manuelles |
| `/api/extract` | POST | Claude extrait le contenu pédagogique |
| `/api/draft` | POST | Claude génère le brouillon module |

### Déploiement

**Backend (Railway)**
1. Connecte le repo GitHub → dossier `backend/`
2. Ajoute les variables d'environnement dans Railway → Variables
3. Railway détecte automatiquement Python et démarre avec le `Procfile`

**Frontend (Vercel)**
1. Connecte le repo GitHub → dossier `frontend/`
2. Aucune variable d'environnement nécessaire
3. Vercel sert `index.html` statiquement

---

## Coûts

| Service | Coût |
|---------|------|
| Vercel | Gratuit |
| Railway | Gratuit (dans les 5$/mois de crédit) |
| Tavily | Gratuit (1000 recherches/mois) |
| Anthropic | Inclus dans l'abonnement équipe |
| GitHub | Gratuit |

**→ Coût total : 0€/mois pour l'équipe**

---

## Sécurité

- La clé API Anthropic n'est **jamais exposée** côté navigateur
- Tous les appels Claude passent par le backend Railway
- Le `TOOL_SECRET` protège les routes backend contre les accès non autorisés
- Ne jamais committer le fichier `.env` sur GitHub (il est dans `.gitignore`)

---

## Contact

Projet développé par **Boutaina** pour l'équipe Creaformation.  
Pour toute question sur l'outil, contacte Boutaina directement.
