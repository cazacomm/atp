# Automatisation du blog — ATP Tarbes

Un article de blog est généré et publié automatiquement **chaque lundi à 9h00 UTC**
par le workflow [`.github/workflows/blog-auto.yml`](../.github/workflows/blog-auto.yml).

## 1. Mettre la clé API en place (à faire une seule fois)

1. Créer une clé sur <https://platform.openai.com/api-keys>.
2. Dans le dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**.
3. Nom : `OPENAI_API_KEY` — Valeur : la clé (`sk-…`).

En ligne de commande :

```bash
gh secret set OPENAI_API_KEY -R cazacomm/atp
```

Sans ce secret, le workflow échoue proprement (code 1) sans rien committer.

## 2. Lancer manuellement

**Depuis GitHub** : onglet *Actions* → *Blog auto — ATP Tarbes* → *Run workflow*.
La case **dry_run** génère l'article et affiche le résultat dans les logs **sans rien écrire ni pousser**.

**En local** :

```bash
pip install openai
export OPENAI_API_KEY="sk-..."

python3 scripts/generate-article.py --dry-run   # simulation, aucun fichier touché
python3 scripts/generate-article.py             # génère et écrit (à committer soi-même)
python3 scripts/generate-article.py --mock      # teste la tuyauterie sans appeler l'API
```

`--mock` ne produit **aucun contenu éditorial réel** : il remplit le gabarit avec un texte
de démonstration pour vérifier que le choix du sujet, la validation, l'assemblage et les
mises à jour de fichiers fonctionnent.

## 3. Codes de sortie

| Code | Signification | Effet sur le workflow |
|---|---|---|
| `0` | Article généré et validé | commit + push |
| `78` | Aucun sujet restant dans `BLOG_WORKFLOW.md`, ou article déjà présent | arrêt propre, pas de commit |
| `1` | Erreur (API, validation, fichier manquant) | échec visible, **aucun fichier écrit** |

## 4. Ce que fait le script

1. Lit `blog-config.json`. Tout ce qui est propre au site y vit — rien de
   spécifique n'est codé en dur dans le script, ce qui permet de le réutiliser
   tel quel sur un autre site en ne changeant que ce fichier. **Dix-neuf clés**
   sont obligatoires et contrôlées au démarrage : `site_name`, `site_url`,
   `sector`, `location`, `geo_keywords`, `tone`, `author`, `target_word_count`,
   `faq_questions_count`, `language`, `model`, `temperature`,
   `topic_marker_prefix`, `og_image`, `logo_path`, `default_article_section`,
   `internal_link_targets`, `reference_article_slug`, `facts`.
   Mieux vaut échouer tout de suite avec un message clair que publier un JSON-LD
   portant le logo d'un autre site.

   `facts` est la **seule source de faits, d'adresses et de coordonnées** que le
   modèle a le droit d'employer : adresse de la salle, téléphone, e-mail, noms
   des coachs et de leur diplôme, liste des cours, équipements. Tout le reste
   doit être reformulé pour s'en passer.

2. Extrait de `BLOG_WORKFLOW.md` les 12 sujets suggérés **et** les règles éditoriales,
   qui sont injectées telles quelles dans le prompt.

   *Convention locale :* dans ce dépôt, le titre du sujet est en gras sur la ligne
   numérotée et **le slug figure entre accents graves sur la ligne suivante**.
   `parse_topics()` lit les deux lignes et **reprend le slug déclaré tel quel** :
   les URLs publiées sont donc exactement celles planifiées dans le document, et
   non un slug redéduit du titre.

3. Scanne `/blog/*/index.html` : un article généré porte un marqueur
   `<!-- atp-topic: N -->` juste après `<body>`. Un sujet marqué n'est jamais repris.

4. Choisit le premier sujet non traité, dans l'ordre de la liste.

5. **Relit l'article de référence** (`blog/preparation-physique-trail-hautes-pyrenees/index.html`)
   et s'en sert de gabarit. Aucun template HTML n'est dupliqué dans le script :
   `<head>`, favicons, polices, feuille de style, header, menu mobile, footer,
   bloc CTA et vague décorative en sont extraits à chaque exécution, donc si le
   gabarit évolue les articles suivants suivent.

   `split_template()` est **adapté aux conventions HTML de ce site** :
   - les trois blocs JSON-LD sont précédés d'un commentaire de section et placés
     juste avant `</head>` — la découpe remonte jusqu'à ce commentaire pour ne
     pas en laisser un orphelin ;
   - le corps vit dans `<main>`, avec un `<nav class="breadcrumb">` en `<ol>`
     puis un `<article class="article">` dont l'en-tête porte l'étiquette de
     catégorie, le `<h1>`, la ligne de méta, l'image de couverture et le chapô ;
   - la FAQ utilise des `<details><summary>`, pas des paragraphes ;
   - le bloc `<div class="article-cta">` **contient lui-même** un
     `<div class="center-btn">` : l'extraction compte les imbrications
     (`_match_div()`), une recherche non gourmande du premier `</div>` le
     tronquerait ;
   - la queue de `<main>` (lien « retour au blog », fermeture de l'article,
     vague décorative) est reprise telle quelle.

   Le texte du CTA du gabarit parle du sujet de l'article de référence : son
   `<h2>` et son premier `<p>` sont donc remplacés par une formulation générique
   construite depuis la configuration. Les boutons, eux, sont conservés.

6. Appelle OpenAI (`gpt-4o`, `temperature` 0.7, `max_tokens` 9000, réponse forcée
   en `json_object`) et lui demande **uniquement le contenu éditorial** :

   ```json
   {"title": …, "h1": …, "breadcrumb": …, "meta_description": …, "lede": …,
    "sections": [{"h2": …, "content": [{"type": "p|h3|ul|ol|strong", "text": …}]}],
    "faq": [{"question": …, "answer": …}]}
   ```

   Le modèle **n'écrit pas une ligne de HTML**. Quand il régénérait la page entière,
   les deux tiers de ses tokens de sortie partaient en balisage (`<head>`, JSON-LD,
   header, footer), ce qui plafonnait le corps rédigé autour de 850 mots quelle que
   soit la consigne.

   Seul balisage autorisé dans les textes : `**gras**` et `[libellé](/chemin)`.
   Les liens sont restreints aux chemins internes, un lien externe est donc
   structurellement impossible. Tout le reste est échappé — le modèle ne peut pas
   injecter de HTML.

7. **Valide le contenu** avant toute écriture : champs présents, longueur du
   `title` (40–70) et de la `meta_description` (< 155), types de blocs connus,
   exactement 5 questions de FAQ, maillage interne (≥ 2 liens vers
   `/planning.html`, `/tarifs.html` ou `/equipeatp.html` et ≥ 1 vers `/blog/`),
   volume entre 900 et 1900 mots, et **garde-fous éditoriaux** : tout symbole
   monétaire, pourcentage chiffré, montant en euros ou date de fondation fait
   échouer la copie. Le moindre échec ⇒ code 1, **rien n'est écrit**.

   Les contrôles sur le canonical, l'Open Graph, la Twitter Card, le marqueur,
   le `<h1>` unique et la validité des JSON-LD **ne sont plus à cette étape** :
   ces éléments sont fabriqués par le script (`json.dumps` pour les JSON-LD) et
   ne peuvent plus être faux. Ils restent vérifiés une fois la page assemblée,
   par `validate_assembled()`, qui contrôle notre propre code et non le modèle —
   dont le nombre de `<details>`, propre à la FAQ de ce site.

   Le volume se compte sur le **contenu** (`content_word_count()`), pas sur du
   HTML : `lede` + sections, FAQ exclue.

   *Rattrapage :* le script relance un appel avec un prompt correctif dès que le
   corps passe **sous la cible de 1200 mots** — même si la validation passerait —
   **ou** qu'une erreur de validation que le modèle peut corriger subsiste
   (maillage interne absent, nombre de questions, longueur du `title`). Le message
   de reprise est construit à partir des erreurs réellement relevées
   (`build_correction()`). Il garde ensuite **la meilleure des copies** : celle qui
   a le moins d'erreurs, puis la plus proche de la cible de volume, et chaque
   reprise repart de la meilleure copie obtenue. Plafond strict : **3 appels**
   (`MAX_CALLS`).

   Le maillage interne est le point sur lequel le modèle achoppe le plus : la
   consigne liste les chemins un par un et montre la forme attendue. Les cibles
   viennent de `internal_link_targets` — elles servent à la fois au prompt, à la
   validation et au message de reprise, et sont tenues courtes (trois cibles).

8. **Assemble la page** : `<head>` repris du gabarit avec seulement les champs
   propres à l'article remplacés (title, description, canonical, keywords, OG,
   Twitter, dates, section), les trois blocs JSON-LD sérialisés depuis le contenu,
   le marqueur d'idempotence inséré après `<body>`, le `<main>` construit de
   toutes pièces, header et footer repris tels quels.

9. Écrit `blog/<slug>/index.html`, puis met à jour `blog/index.html` (carte + JSON-LD),
   `sitemap.xml`, `rss.xml` et `llms.txt`.

## 4 bis. Réécrire un article existant

```bash
python scripts/generate-article.py --rewrite <slug>
```

Régénère un article déjà publié et **écrase** son fichier. Le sujet est retrouvé
via le marqueur `<!-- atp-topic: N -->` présent dans le fichier, donc aucun
risque de se tromper de sujet. Le teaser de `blog/index.html` et l'entrée
`rss.xml` sont resynchronisés (`refresh_entries()`) : les updaters normaux sont
idempotents par URL et laisseraient sinon le texte de l'ancienne version.

Disponible aussi depuis Actions : champ **rewrite** du `workflow_dispatch`.

> L'article de référence `preparation-physique-trail-hautes-pyrenees` a été écrit
> à la main et sert de gabarit : il ne porte pas de marqueur et ne peut donc pas
> être réécrit par cette commande. C'est voulu.

## 5. Idempotence

- Le slug vient de `BLOG_WORKFLOW.md` (ou, à défaut, est déduit du titre de façon
  **déterministe**) : même sujet ⇒ même slug.
- Si `blog/<slug>/index.html` existe déjà, le script s'arrête en code 78 sans rien écraser.
- Les mises à jour de `blog/index.html`, `sitemap.xml`, `rss.xml` et `llms.txt` vérifient
  d'abord si l'URL est déjà présente : rejouer le workflow ne crée jamais de doublon.
- Aucun article existant n'est jamais modifié ni supprimé.

## 6. Coût estimé

Tarifs OpenAI `gpt-4o` en vigueur à la mise en place — **à revérifier sur
<https://openai.com/api/pricing/>**, ils changent.

Par exécution : environ **4 000 à 5 000 tokens en entrée** par appel et **5 000 à
7 000 tokens en sortie**, multipliés par le nombre d'appels réellement effectués
(1 à 3, plafonné par `MAX_CALLS`).

L'ordre de grandeur est de **quelques dizaines de centimes d'euro par article** avec
`gpt-4o`, soit quelques euros par an pour une publication hebdomadaire. Le poste de
coût réel n'est pas l'API mais la relecture humaine.

Pour vérifier la consommation réelle : les logs du workflow affichent le décompte exact
des tokens de chaque exécution (`[blog] Tokens : … entrée + … sortie = …`) et le nombre
d'appels (`[blog] N appels OpenAI au total pour cet article.`).

## 7. Ajouter des sujets

La réserve de sujets est la section **« 12 sujets d'articles suggérés »** de
[`BLOG_WORKFLOW.md`](../BLOG_WORKFLOW.md). Quand elle est épuisée, le workflow sort en
code 78 chaque lundi sans rien casser. Il suffit d'ajouter des entrées au même
format pour relancer la machine :

```markdown
13. **Titre du sujet**
    `slug-du-sujet`
```

## 8. Relecture

La génération est automatique, la responsabilité éditoriale ne l'est pas.
Après chaque publication, vérifier au minimum : aucun prix ni chiffre inventé, adresse
et coordonnées exactes, aucune affirmation médicale, ton conforme. Les règles complètes
sont dans `BLOG_WORKFLOW.md`, section « Règles éditoriales ».
