# BLOG_WORKFLOW — ATP Tarbes

Procédure pour publier un nouvel article sur https://atptarbes.fr/blog/.
Le blog est en HTML statique (GitHub Pages) : **aucun build, aucun CMS**.
Publier = ajouter un dossier, mettre à jour 4 fichiers, commit, push.

---

## 1. Architecture

```
/assets/blog.css                     ← styles du blog (charte identique au site)
/blog/index.html                     ← page listing des articles
/blog/<slug>/index.html              ← un dossier par article
/sitemap.xml                         ← à mettre à jour à chaque publication
/rss.xml                             ← à mettre à jour à chaque publication
/llms.txt                            ← à mettre à jour à chaque publication
/robots.txt                          ← ne bouge plus
```

**Règle d'URL** : un article vit dans son propre dossier avec un `index.html`,
ce qui donne une URL propre terminée par `/` :
`https://atptarbes.fr/blog/mon-sujet-principal/`

**Forme canonique** : toujours `https://atptarbes.fr/...` (apex, HTTPS, sans `www`),
conformément au `CNAME`. Ne jamais canonicaliser vers `www.atptarbes.fr` ni vers
l'URL `*.github.io`.

---

## 2. Publier un nouvel article (checklist)

### 2.1 Créer le fichier

1. Choisir un **slug** court, en minuscules, sans accent, mots séparés par des tirets.
   Exemple : `reprendre-le-sport-apres-40-ans-tarbes`.
2. Dupliquer le dossier `/blog/preparation-physique-trail-hautes-pyrenees/`
   et le renommer avec le nouveau slug.
3. Dans le nouvel `index.html`, remplacer :
   - `<title>` (≈ 60 caractères, avec « | ATP Tarbes »)
   - `<meta name="description">` — **strictement moins de 155 caractères**
   - `<link rel="canonical">` → nouvelle URL complète
   - `og:title`, `og:description`, `og:url`, `og:image`, `article:published_time`
   - `twitter:title`, `twitter:description`, `twitter:image`
   - `<meta name="keywords">` (garder les ancrages locaux : Tarbes, Hautes-Pyrénées, 65)
   - le bloc JSON-LD **Article** (headline, description, image, datePublished,
     dateModified, `mainEntityOfPage.@id`)
   - le bloc JSON-LD **BreadcrumbList** (3e niveau : titre + URL de l'article)
   - le bloc JSON-LD **FAQPage** (5 questions/réponses)
   - le fil d'Ariane HTML, le `<h1>`, la date affichée, le contenu

> Le HTML visible de la FAQ (`<details>`) et le JSON-LD FAQPage doivent dire
> **exactement la même chose**. Un décalage entre les deux est une cause classique
> de perte du rich result.

### 2.2 Référencer l'article

4. **`/blog/index.html`** : ajouter une `<article class="post-card">` en haut de la
   grille (les plus récents en premier) + ajouter l'entrée dans le tableau
   `blogPost` du JSON-LD.
5. **`/sitemap.xml`** : ajouter un bloc `<url>` avec la date du jour en `lastmod`,
   `changefreq: monthly`, `priority: 0.7`. Mettre aussi à jour le `lastmod` de `/blog/`.
6. **`/rss.xml`** : ajouter un `<item>` en tête de `<channel>` et actualiser
   `<lastBuildDate>` (format RFC-822, ex. `Sat, 15 Aug 2026 09:00:00 +0200`).
7. **`/llms.txt`** : ajouter l'article sous la section `## Blog` avec un résumé
   d'une à deux phrases.

### 2.3 Vérifier avant publication

- [ ] La meta description fait **< 155 caractères**.
- [ ] Un seul `<h1>` sur la page, hiérarchie H2 / H3 cohérente.
- [ ] Toutes les URLs internes sont **absolues depuis la racine** (`/tarifs.html`,
      `/atp/photo.jpg`) — un lien relatif casse depuis `/blog/<slug>/`.
- [ ] L'image de couverture existe réellement dans `/atp/` (vérifier le nom exact).
- [ ] Les trois blocs JSON-LD passent le
      [Rich Results Test](https://search.google.com/test/rich-results).
- [ ] Rendu correct sur mobile (le header passe en burger sous 900 px).
- [ ] Le lien « Blog » du footer est présent (il l'est déjà sur toutes les pages).

### 2.4 Publier

```bash
git add blog/ sitemap.xml rss.xml llms.txt
git commit -m "feat(blog): <titre de l'article>"
git push origin main
```

GitHub Pages redéploie automatiquement (compter quelques minutes).
Ensuite : soumettre l'URL dans la Google Search Console (« Inspection de l'URL »
→ « Demander une indexation »).

---

## 3. Règles éditoriales

**Longueur** : 1 200 à 1 500 mots. En dessous, l'article a peu de chances de
ressortir sur des requêtes concurrentielles ; au-dessus, il se dilue.

**Structure type** :
- une accroche (`article-lede`) qui pose le contexte local en 3-4 phrases ;
- 4 à 6 `<h2>`, avec des `<h3>` quand la section le justifie ;
- un `<div class="callout">` pour le point clé à retenir ;
- une FAQ de **5 questions** — ce sont elles qui alimentent les réponses des
  moteurs génératifs (ChatGPT, Perplexity, Claude, AI Overviews) ;
- un bloc `article-cta` en fin d'article.

**Ancrage local** : chaque article doit mentionner naturellement Tarbes et la zone
(Hautes-Pyrénées, Bagnères, Lourdes, vallée d'Aure, Pau…). Sans forcer : un article
qui répète « salle de sport à Tarbes » à chaque paragraphe se lit mal et se
positionne moins bien qu'un texte utile.

**Interdits absolus** :
- ❌ inventer un **prix**, un **tarif** ou une **promotion** → renvoyer vers `/tarifs.html` ;
- ❌ inventer des **chiffres précis** (nombre d'adhérents, pourcentages de
  progression, statistiques d'étude non sourcée) ;
- ❌ citer un **nom de client ou d'adhérent** sans accord écrit ;
- ❌ énoncer une **règle médicale ou réglementaire** comme un fait établi
  (certificat médical, obligations légales, contre-indications) ;
- ❌ inventer des **dates** (création de la salle, ancienneté, palmarès).

En cas de doute sur un chiffre : reformuler en qualitatif (« la plupart des
pratiquants », « souvent », « selon le niveau ») plutôt que d'inventer une valeur.

**Ton** : celui du site — direct, technique mais accessible, pas de survente.
La promesse est le sérieux de l'encadrement, pas le miracle.

---

## 4. Cohérence NAP

Les coordonnées doivent être **identiques partout** (site, JSON-LD, `llms.txt`,
Google Business Profile, réseaux sociaux, annuaires) :

```
ATP Tarbes (Athletic Training Performance)
1 rue Youri Gagarine — Centre de gros zone Kennedy
65000 Tarbes
+33 6 87 57 68 69
atppreparationphysique@gmail.com
https://atptarbes.fr/
```

Toute modification d'une de ces valeurs doit être répercutée dans :
`index.html`, `tarifs.html`, `planning.html`, `salle.html`, `avis.html`,
`equipeatp.html`, `mentions.html`, `/blog/index.html`, chaque article, et `llms.txt`.

---

## 5. Fichiers d'exposition aux moteurs de réponse

- **`robots.txt`** : autorise explicitement Googlebot, Bingbot, Applebot, GPTBot,
  OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-User, Claude-SearchBot,
  PerplexityBot, Perplexity-User, Google-Extended, Applebot-Extended,
  MistralAI-User, Meta-ExternalAgent, Amazonbot. Bloque CCBot et Bytespider.
- **`llms.txt`** : fiche d'identité lisible par les LLM (NAP, activités, pages,
  articles). C'est le fichier qui limite les réponses approximatives sur ATP.
- **`rss.xml`** : flux du blog, utile pour les agrégateurs et la syndication.

---

## 6. 12 sujets d'articles suggérés

Ordre indicatif de priorité (intention de recherche locale × facilité de rédaction).

1. **Reprendre le sport après 40 ans à Tarbes : par où commencer**
   `reprendre-le-sport-apres-40-ans-tarbes`
2. **Préparation physique ou musculation : quelle différence et laquelle choisir**
   `preparation-physique-ou-musculation-difference`
3. **Se préparer à une Hyrox : les qualités physiques à développer**
   `preparation-hyrox-tarbes`
4. **Mal de dos et sédentarité : quels exercices pour se remettre en mouvement**
   `mal-de-dos-exercices-remise-en-mouvement`
5. **Entraînement fonctionnel : ce que ça veut dire concrètement**
   `entrainement-fonctionnel-definition`
6. **Combien de séances par semaine pour progresser vraiment**
   `combien-de-seances-par-semaine-progresser`
7. **Bien débuter en salle : les 7 erreurs des premières semaines**
   `debuter-en-salle-erreurs-frequentes`
8. **Préparer la saison de ski et de raquettes dans les Pyrénées**
   `preparation-physique-ski-pyrenees`
9. **Course à pied : comment éviter les blessures récurrentes**
   `course-a-pied-eviter-blessures`
10. **Gainage : pourquoi la planche ne suffit pas**
    `gainage-au-dela-de-la-planche`
11. **Sport en été à Tarbes : s'entraîner malgré la chaleur**
    `sentrainer-malgre-la-chaleur-tarbes`
12. **Coaching individuel ou cours collectif : comment choisir**
    `coaching-individuel-ou-cours-collectif`

Pour chaque sujet : vérifier avant rédaction qu'il ne cannibalise pas un article
déjà publié (même intention de recherche = fusionner plutôt que dupliquer).

---

*Dernière mise à jour : 15 août 2026.*
