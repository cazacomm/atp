# Génération automatique d'articles — ATP Tarbes

Un article de blog est rédigé et publié **chaque lundi à 09:00 UTC**, sans
intervention. Le workflow lit la liste des sujets de `BLOG_WORKFLOW.md`, prend
le premier sujet non traité, appelle l'API OpenAI, assemble l'article à partir
du **gabarit relu dans `/blog/`**, puis commite et pousse.

| Fichier | Rôle |
|---|---|
| `blog-config.json` | Identité du site, ton, sujets, images, modèle OpenAI |
| `scripts/generate-article.py` | Génération, validation, assemblage, mises à jour |
| `.github/workflows/blog-auto.yml` | Planification hebdomadaire + déclenchement manuel |
| `BLOG_WORKFLOW.md` | Source des sujets **et** des règles éditoriales |

---

## 1. Ajouter la clé API (à faire une fois)

1. Créer une clé sur <https://platform.openai.com/api-keys>.
2. Sur GitHub : **Settings → Secrets and variables → Actions → New repository secret**
3. Nom exact : `OPENAI_API_KEY` — valeur : la clé (`sk-…`).

Sans ce secret, le workflow s'arrête proprement avec un message explicite ;
aucun commit n'est produit.

## 2. Lancer manuellement

**Depuis GitHub** : onglet *Actions* → « Blog — article automatique » →
*Run workflow*. Deux options facultatives : `dry_run` (aucune écriture) et
`topic` (forcer un numéro de sujet).

**En local** :

```bash
pip install openai
export OPENAI_API_KEY="sk-…"

python3 scripts/generate-article.py --dry-run   # test complet, n'écrit rien
python3 scripts/generate-article.py             # génère et écrit
python3 scripts/generate-article.py --topic 4   # force le sujet n°4
python3 scripts/generate-article.py --mock      # test hors ligne, sans clé API
```

`--mock` produit un contenu de démonstration sans appeler l'API : utile pour
vérifier le gabarit, les métadonnées et les données structurées. Il force
toujours `--dry-run`, donc rien n'est jamais écrit sur disque.

## 3. Codes de sortie

| Code | Signification | Effet sur le workflow |
|---|---|---|
| `0` | Article généré | commit + push |
| `78` | Plus aucun sujet à traiter | job vert, aucun commit |
| `1` | Erreur (clé absente, API en échec, contenu refusé, gabarit modifié) | job rouge, aucun commit |

## 4. Garde-fous

- **Idempotence** : chaque article contient `<!-- atp-topic: N -->`. Un sujet
  déjà marqué, ou dont le dossier `/blog/<slug>/` existe, est ignoré. Rejouer le
  workflow ne réécrit jamais un article existant — le script s'arrête avant.
- **Aucune modification d'existant** : le script n'écrit que le nouvel article,
  et ajoute (sans rien supprimer) une carte dans `/blog/index.html`, une entrée
  dans `sitemap.xml` et un item dans `rss.xml`. Les insertions sont ignorées si
  l'URL est déjà présente.
- **Validation avant écriture** : meta description < 155 caractères, exactement
  5 questions de FAQ, longueur du corps dans la fourchette, un seul `<h1>`,
  JSON-LD reparsé. Tout symbole `€`, pourcentage chiffré, montant en euros ou
  date de création fait **échouer** la génération (règles de `BLOG_WORKFLOW.md`).
- **Gabarit non dupliqué** : il est relu dans `/blog/` à chaque exécution. Si sa
  structure change au point de casser une ancre, le script s'arrête avec le nom
  de l'ancre manquante plutôt que de produire un fichier incohérent.

## 5. Coût estimé

Modèle `gpt-4o-mini`, un appel par article (≈ 1 200 tokens en entrée,
≈ 2 500 en sortie).

**Ordre de grandeur : moins d'un centime d'euro par article**, soit quelques
centimes par an pour une publication hebdomadaire. Le coût réel dépend de la
tarification OpenAI en vigueur — à vérifier sur
<https://openai.com/api/pricing/>. GitHub Actions est gratuit sur dépôt public.

## 6. Quand les 12 sujets seront épuisés

Le workflow sortira en `78` chaque semaine sans rien publier. Pour relancer la
machine, ajouter des sujets dans la section « sujets d'articles suggérés » de
`BLOG_WORKFLOW.md`, au même format :

```markdown
13. **Titre de l'article**
    `slug-de-l-article`
```
