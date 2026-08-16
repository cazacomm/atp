#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate-article.py — Génération automatique d'un article de blog.

Principe : le gabarit HTML n'est PAS dupliqué dans ce script. Il est relu à
chaque exécution depuis un article existant du dossier /blog/, puis ses zones
sont remplacées une par une. Toute évolution du design de l'article de
référence est donc reprise automatiquement par les articles suivants.

Codes de sortie :
    0   succès (article généré, ou dry-run réussi)
    1   erreur (config, gabarit, API, validation, écriture)
    78  aucun nouveau sujet à traiter (EX_CONFIG — arrêt propre, pas une erreur)

Usage :
    python3 scripts/generate-article.py                 # génère et écrit
    python3 scripts/generate-article.py --dry-run       # n'écrit rien
    python3 scripts/generate-article.py --mock          # sans réseau (test), implique --dry-run
    python3 scripts/generate-article.py --topic 3       # force le sujet n°3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_TOPIC = 78

ROOT = Path(__file__).resolve().parent.parent

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_RFC = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MOIS_RFC = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ───────────────────────────── utilitaires ─────────────────────────────

def log(msg: str = "") -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    log(f"\n── {msg}")


def die(msg: str, code: int = EXIT_ERROR):
    log(f"\n✖ ERREUR : {msg}")
    sys.exit(code)


class Anchor(Exception):
    """Ancre introuvable dans le gabarit."""


def sub1(pattern: str, repl, text: str, label: str, flags=0) -> str:
    """Substitution qui exige exactement une occurrence (sinon le gabarit a changé)."""
    new, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise Anchor(f"ancre « {label} » introuvable dans le gabarit "
                     f"(motif : {pattern[:70]}…)")
    return new


def esc(s: str) -> str:
    """Échappe pour un attribut HTML."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def lit(s: str) -> str:
    """Rend une chaîne utilisable comme remplacement re.sub (protège les \\1, \\g...)."""
    return s.replace("\\", "\\\\")


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def word_count(html: str) -> int:
    return len(strip_tags(html).split())


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", value)


def date_fr(d: datetime) -> str:
    return f"{d.day} {MOIS_FR[d.month - 1]} {d.year}"


def date_rfc822(d: datetime) -> str:
    return (f"{JOURS_RFC[d.weekday()]}, {d.day:02d} {MOIS_RFC[d.month - 1]} {d.year} "
            f"{d.hour:02d}:{d.minute:02d}:{d.second:02d} +0200")


# ───────────────────────────── configuration ─────────────────────────────

def load_config(path: Path) -> dict:
    if not path.exists():
        die(f"configuration introuvable : {path}")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"blog-config.json illisible : {e}")
    for key in ("site_name", "site_url", "site_slug", "location", "author"):
        if not cfg.get(key):
            die(f"clé obligatoire manquante dans blog-config.json : {key}")
    cfg["site_url"] = cfg["site_url"].rstrip("/")
    return cfg


# ───────────────────────────── sujets ─────────────────────────────

TOPIC_RE = re.compile(
    r"^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*\n\s*`([a-z0-9\-]+)`",
    re.MULTILINE,
)


def parse_topics(workflow_path: Path) -> list[dict]:
    """Extrait la liste numérotée « sujets suggérés » de BLOG_WORKFLOW.md."""
    if not workflow_path.exists():
        die(f"{workflow_path.name} introuvable — impossible de lire la liste des sujets")
    md = workflow_path.read_text(encoding="utf-8")

    # On se limite à la section des sujets suggérés si elle est identifiable.
    m = re.search(r"^##\s+.*sujets d'articles suggérés.*$", md, re.MULTILINE | re.IGNORECASE)
    if m:
        section = md[m.end():]
        nxt = re.search(r"^##\s+", section, re.MULTILINE)
        if nxt:
            section = section[:nxt.start()]
    else:
        section = md

    topics = [{"n": int(n), "title": t.strip(), "slug": s.strip()}
              for n, t, s in TOPIC_RE.findall(section)]
    if not topics:
        die("aucun sujet trouvé dans BLOG_WORKFLOW.md "
            "(format attendu : `1. **Titre**` puis une ligne `` `slug` ``)")
    topics.sort(key=lambda x: x["n"])
    return topics


MARKER_RE_TMPL = r"<!--\s*{slug}-topic:\s*(\d+)\s*-->"


def scan_existing(blog_dir: Path, site_slug: str) -> tuple[set[str], set[int]]:
    """Renvoie (slugs d'articles publiés, numéros de sujets déjà traités)."""
    slugs, markers = set(), set()
    if not blog_dir.exists():
        die(f"dossier blog introuvable : {blog_dir}")
    marker_re = re.compile(MARKER_RE_TMPL.format(slug=re.escape(site_slug)))
    for page in sorted(blog_dir.glob("*/index.html")):
        slugs.add(page.parent.name)
        for found in marker_re.findall(page.read_text(encoding="utf-8")):
            markers.add(int(found))
    return slugs, markers


def pick_topic(topics: list[dict], slugs: set[str], markers: set[int],
               forced: int | None) -> dict:
    if forced is not None:
        for t in topics:
            if t["n"] == forced:
                if t["slug"] in slugs or t["n"] in markers:
                    die(f"sujet n°{forced} déjà traité "
                        f"(dossier /blog/{t['slug']}/ ou marqueur présent)")
                return t
        die(f"sujet n°{forced} absent de la liste BLOG_WORKFLOW.md")

    for t in topics:
        if t["slug"] in slugs:
            log(f"   · sujet {t['n']:>2} — déjà publié (/blog/{t['slug']}/)")
            continue
        if t["n"] in markers:
            log(f"   · sujet {t['n']:>2} — marqueur déjà présent, ignoré")
            continue
        return t

    log("\n✔ Tous les sujets de BLOG_WORKFLOW.md sont déjà publiés. Rien à faire.")
    log("   Ajoutez de nouveaux sujets dans la section « sujets d'articles suggérés ».")
    sys.exit(EXIT_NO_TOPIC)


# ───────────────────────────── gabarit ─────────────────────────────

def load_template(cfg: dict, blog_dir: Path) -> tuple[str, str]:
    """Relit le gabarit depuis un article existant (jamais dupliqué ici)."""
    preferred = cfg.get("template_article_slug")
    candidates = []
    if preferred:
        candidates.append(blog_dir / preferred / "index.html")
    candidates += sorted(blog_dir.glob("*/index.html"))

    for c in candidates:
        if c.exists():
            try:
                shown = "/" + c.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                shown = c.as_posix()
            log(f"   gabarit relu depuis : {shown}")
            return c.read_text(encoding="utf-8"), c.parent.name
    die("aucun article existant pour servir de gabarit dans /blog/")


# ───────────────────────────── OpenAI ─────────────────────────────

SYSTEM_PROMPT = """Tu es rédacteur SEO senior pour une entreprise locale française.
Tu écris des articles de blog utiles, précis et vérifiables, jamais promotionnels.
Tu réponds UNIQUEMENT par un objet JSON valide, sans texte autour, sans bloc de code."""


def build_user_prompt(cfg: dict, topic: dict, editorial_rules: str) -> str:
    geo = ", ".join(cfg.get("geo_keywords", [])[:12])
    bans = "\n".join(f"- {b}" for b in cfg.get("editorial_bans", []))
    return f"""Rédige un article de blog complet en {cfg.get('language', 'fr')}.

ENTREPRISE
- Nom : {cfg['site_name']}
- Secteur : {cfg['sector']}
- Localisation : {cfg['location']}
- Ancrages géographiques utilisables : {geo}
- Ton attendu : {cfg['tone']}

SUJET IMPOSÉ
- Titre de travail : {topic['title']}
- Slug d'URL (déjà fixé, ne pas le changer) : {topic['slug']}

CONTRAINTES DE FOND — INTERDICTIONS ABSOLUES
{bans}
Tu ne dois JAMAIS inventer : un prix, un tarif, une promotion, un pourcentage,
une statistique, un nombre d'adhérents, un nom de client, une date de création,
une règle médicale ou réglementaire présentée comme un fait établi.
En cas de doute sur un chiffre, écris-le en qualitatif (« la plupart »,
« souvent », « selon le niveau »). Aucun symbole € ni % dans le texte.
Pour tout ce qui touche aux tarifs ou aux horaires, renvoie le lecteur vers les
pages du site plutôt que d'annoncer une valeur.

RÈGLES ÉDITORIALES DU SITE (extraites de BLOG_WORKFLOW.md)
{editorial_rules}

STRUCTURE DEMANDÉE
- Environ {cfg.get('target_word_count', 1300)} mots pour le corps (hors FAQ), fourchette 1200-1500.
- 4 à 6 sections <h2>, avec des <h3> quand la section le justifie.
- Exactement un encadré <div class="callout"><p>…</p></div> avec le point clé à retenir.
- Au moins une liste <ul> avec des <li>.
- Ancrage local naturel (ville et région citées sans matraquage).
- Pas de conclusion creuse : la dernière section doit apporter du concret.

FORMAT DE RÉPONSE — objet JSON avec exactement ces clés :
{{
  "title": "titre H1, 60-90 caractères, sans nom de marque",
  "meta_title": "balise <title>, moins de 65 caractères, se terminant par ' | {cfg['site_name'].split('(')[0].strip()}'",
  "meta_description": "moins de 150 caractères, incitative, avec la ville",
  "keywords": "15 à 25 mots-clés séparés par des virgules, incluant les ancrages locaux",
  "category": "catégorie courte affichée en étiquette, 1 à 3 mots",
  "lede": "chapô de 3 à 4 phrases, texte brut sans balise",
  "body_html": "le corps de l'article en HTML : uniquement <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em> et un <div class=\\"callout\\"><p>…</p></div>. Pas de <h1>, pas de <section>, pas d'attribut style, pas de lien externe.",
  "faq": [
    {{"question": "…", "answer": "réponse de 2 à 4 phrases, texte brut sans balise"}}
  ],
  "cta_heading": "titre du bloc d'appel à l'action, 4 à 8 mots",
  "cta_text": "1 à 2 phrases invitant à venir sur place, sans prix ni promotion",
  "image_alt": "description de la photo d'illustration, 8 à 15 mots",
  "reading_minutes": 7
}}

La clé "faq" doit contenir exactement {cfg.get('faq_questions_count', 5)} entrées."""


def extract_editorial_rules(workflow_path: Path) -> str:
    """Extrait la section « Règles éditoriales » de BLOG_WORKFLOW.md pour le prompt."""
    if not workflow_path.exists():
        return ""
    md = workflow_path.read_text(encoding="utf-8")
    m = re.search(r"^##\s+.*Règles éditoriales.*$", md, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    section = md[m.end():]
    nxt = re.search(r"^##\s+", section, re.MULTILINE)
    if nxt:
        section = section[:nxt.start()]
    return section.strip()[:2500]


def call_openai(cfg: dict, topic: dict, editorial_rules: str, retries: int = 3) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        die("variable d'environnement OPENAI_API_KEY absente ou vide "
            "(secret GitHub « OPENAI_API_KEY »). Utilisez --mock pour tester hors ligne.")
    try:
        from openai import OpenAI
    except ImportError:
        die("paquet « openai » non installé — exécutez : pip install openai")

    client = OpenAI(api_key=api_key)
    model = cfg.get("openai_model", "gpt-4o-mini")
    temperature = float(cfg.get("openai_temperature", 0.7))
    user_prompt = build_user_prompt(cfg, topic, editorial_rules)

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            log(f"   appel OpenAI ({model}, temperature={temperature}) — tentative {attempt}/{retries}")
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = resp.choices[0].message.content
            usage = getattr(resp, "usage", None)
            if usage:
                log(f"   tokens : {usage.prompt_tokens} entrée / "
                    f"{usage.completion_tokens} sortie")
            return json.loads(raw)
        except json.JSONDecodeError as e:
            last_err = f"réponse non-JSON du modèle : {e}"
        except Exception as e:                      # noqa: BLE001 — on retente sur tout
            last_err = f"{type(e).__name__}: {e}"
        log(f"   ! échec ({last_err})")
        if attempt < retries:
            wait = 5 * attempt
            log(f"   nouvelle tentative dans {wait}s…")
            time.sleep(wait)

    die(f"appel OpenAI en échec après {retries} tentatives — {last_err}")


def mock_payload(cfg: dict, topic: dict) -> dict:
    """Charge utile de test (--mock) : sert uniquement à vérifier l'assemblage HTML.

    Le texte est un remplissage explicite, calibré pour atteindre la longueur
    cible afin que la validation et l'assemblage soient réellement exercés.
    Il n'est jamais écrit sur disque : --mock force --dry-run.
    """
    ville = cfg["location"].split(",")[0].strip()
    target = cfg.get("target_word_count", 1300)

    filler = (f"Ce paragraphe est un texte de démonstration destiné à vérifier la mise en "
              f"page de l'article, l'ancrage local à {ville} et le calibrage de la longueur. "
              "Il ne contient aucune information réelle et ne doit jamais être publié en "
              "l'état. Le contenu définitif est produit par le modèle lors d'une exécution "
              "normale du script, à partir des règles éditoriales du site. ")

    def para(n: int) -> str:
        return "<p>" + (filler * n).strip() + "</p>"

    p = ("<h2>Pourquoi la question se pose</h2>"
         f"<p>Contenu de démonstration pour le sujet « {topic['title']} » à {ville}. "
         "Ce texte sert à valider le rendu HTML, les métadonnées et les données "
         "structurées avant tout appel réel au modèle.</p>"
         + para(3) +
         "<h2>Ce que l'on observe sur le terrain</h2>"
         + para(3) +
         "<h3>Un premier point de détail</h3>"
         + para(3) +
         "<h3>Un second point de détail</h3>"
         + para(2) +
         '<div class="callout"><p><strong>À retenir :</strong> ceci est un encadré de '
         "démonstration, remplacé par le point clé réel en exécution normale.</p></div>"
         "<h2>Comment s'organiser</h2>"
         + para(2) +
         "<ul><li>Premier élément de démonstration.</li>"
         "<li>Deuxième élément de démonstration.</li>"
         "<li>Troisième élément de démonstration.</li></ul>"
         "<h2>Les erreurs fréquentes</h2>"
         + para(3) +
         "<h2>Passer à la pratique</h2>"
         + para(2))

    # complément pour approcher la cible de mots sans dépasser la borne haute
    while word_count(p) < target - 60:
        p += para(1)
    return {
        "title": topic["title"],
        "meta_title": f"{topic['title']} | {cfg['site_name'].split('(')[0].strip()}",
        "meta_description": f"{topic['title']} : les conseils des coachs à {ville}.",
        "keywords": f"{topic['slug'].replace('-', ' ')}, {ville.lower()}, "
                    f"préparation physique {ville.lower()}, coach sportif {ville.lower()}",
        "category": "Conseils",
        "lede": "Chapô de démonstration généré en mode --mock, sans appel réseau.",
        "body_html": p,
        "faq": [{"question": f"Question de démonstration n°{i} ?",
                 "answer": "Réponse de démonstration en mode test."}
                for i in range(1, cfg.get("faq_questions_count", 5) + 1)],
        "cta_heading": "Envie d'en parler avec un coach ?",
        "cta_text": f"Les coachs vous accueillent à {ville} pour faire le point sur vos objectifs.",
        "image_alt": f"Séance d'entraînement encadrée chez {cfg['site_name'].split('(')[0].strip()}",
        "reading_minutes": 7,
    }


# ───────────────────────────── validation ─────────────────────────────

FORBIDDEN_PATTERNS = [
    (r"[€$]", "symbole monétaire"),
    (r"\d\s*%", "pourcentage chiffré"),
    (r"\b\d+\s*(?:euros?|eur)\b", "montant en euros"),
    (r"\bdepuis\s+(?:19|20)\d{2}\b", "date de création"),
    (r"\bfondée?\s+en\s+(?:19|20)\d{2}\b", "date de création"),
]

REQUIRED_KEYS = ("title", "meta_title", "meta_description", "keywords", "category",
                 "lede", "body_html", "faq", "cta_heading", "cta_text", "image_alt")

ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "em", "br", "div"}


def validate(payload: dict, cfg: dict) -> list[str]:
    """Retourne la liste des avertissements ; lève ValueError sur faute bloquante."""
    warn: list[str] = []

    missing = [k for k in REQUIRED_KEYS if not payload.get(k)]
    if missing:
        raise ValueError(f"clés manquantes dans la réponse du modèle : {', '.join(missing)}")

    want = cfg.get("faq_questions_count", 5)
    faq = payload["faq"]
    if not isinstance(faq, list) or len(faq) != want:
        raise ValueError(f"la FAQ doit contenir exactement {want} entrées "
                         f"(reçu : {len(faq) if isinstance(faq, list) else type(faq).__name__})")
    for i, qa in enumerate(faq, 1):
        if not isinstance(qa, dict) or not qa.get("question") or not qa.get("answer"):
            raise ValueError(f"entrée FAQ n°{i} incomplète")

    desc = payload["meta_description"].strip()
    if len(desc) >= 155:
        raise ValueError(f"meta description trop longue : {len(desc)} caractères (max 154)")

    body = payload["body_html"]
    wc = word_count(body)
    if wc < 700:
        raise ValueError(f"corps trop court : {wc} mots")
    if wc > 2200:
        raise ValueError(f"corps trop long : {wc} mots")
    target = cfg.get("target_word_count", 1300)
    if not (target * 0.85 <= wc <= target * 1.25):
        warn.append(f"corps à {wc} mots, hors de la cible {target} (±)")

    if "<h1" in body.lower():
        raise ValueError("le corps contient un <h1> (il doit être unique et géré par le gabarit)")
    if re.search(r"<a\s", body, re.I):
        warn.append("le corps contient un lien : vérifier sa pertinence")
    if 'class="callout"' not in body:
        warn.append("aucun encadré callout dans le corps")

    used = {t.lower() for t in re.findall(r"<\s*([a-zA-Z0-9]+)", body)}
    unexpected = used - ALLOWED_TAGS
    if unexpected:
        warn.append(f"balises inattendues dans le corps : {', '.join(sorted(unexpected))}")

    haystack = " ".join([body, payload["lede"], desc, payload["cta_text"],
                         " ".join(f"{q['question']} {q['answer']}" for q in faq)])
    for pattern, label in FORBIDDEN_PATTERNS:
        m = re.search(pattern, haystack, re.I)
        if m:
            raise ValueError(f"contenu interdit détecté ({label}) : « {m.group(0)} »")

    ville = cfg["location"].split(",")[0].strip().lower()
    if ville not in (body + payload["lede"]).lower():
        warn.append(f"la ville « {ville} » n'apparaît pas dans le corps — ancrage local faible")

    return warn


# ───────────────────────────── assemblage HTML ─────────────────────────────

def build_article_html(template: str, cfg: dict, topic: dict, payload: dict,
                       now: datetime, cover: str) -> str:
    base = cfg["site_url"]
    url = f"{base}/blog/{topic['slug']}/"
    iso = now.strftime("%Y-%m-%d")
    human = date_fr(now)
    title = payload["title"].strip()
    desc = payload["meta_description"].strip()
    minutes = int(payload.get("reading_minutes") or 7)
    cover_url = f"{base}{cover}"
    html = template

    # ---- <head> ----
    html = sub1(r"<title>.*?</title>", lit(f"<title>{esc(payload['meta_title'].strip())}</title>"),
                html, "title", re.S)
    html = sub1(r'(<meta name="description"\s*\n?\s*content=")(?:.*?)(")',
                lambda m: m.group(1) + esc(desc) + m.group(2), html, "meta description", re.S)
    html = sub1(r'(<link rel="canonical" href=")[^"]*(")',
                lambda m: m.group(1) + url + m.group(2), html, "canonical")
    html = sub1(r'(<meta name="keywords"\s*\n?\s*content=")(?:.*?)(")',
                lambda m: m.group(1) + esc(payload["keywords"].strip()) + m.group(2),
                html, "keywords", re.S)

    for prop, value in [
        ("og:title", title),
        ("og:description", desc),
        ("og:url", url),
        ("og:image", cover_url),
        ("og:image:alt", payload["image_alt"].strip()),
        ("article:published_time", iso),
        ("article:section", payload["category"].strip()),
    ]:
        html = sub1(rf'(<meta property="{re.escape(prop)}" content=")[^"]*(")',
                    lambda m, v=value: m.group(1) + esc(v) + m.group(2), html, prop)

    for name, value in [
        ("twitter:title", title),
        ("twitter:description", desc),
        ("twitter:image", cover_url),
        ("twitter:image:alt", payload["image_alt"].strip()),
    ]:
        html = sub1(rf'(<meta name="{re.escape(name)}" content=")[^"]*(")',
                    lambda m, v=value: m.group(1) + esc(v) + m.group(2), html, name)

    # ---- JSON-LD : les 3 blocs sont régénérés (garantie de validité) ----
    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": desc,
        "image": cover_url,
        "inLanguage": "fr-FR",
        "datePublished": iso,
        "dateModified": iso,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "articleSection": payload["category"].strip(),
        "keywords": payload["keywords"].strip(),
        "author": {"@type": "Organization", "name": cfg["site_name"].split("(")[0].strip(),
                   "url": f"{base}/"},
        "publisher": {
            "@type": "Organization",
            "name": cfg["site_name"].split("(")[0].strip(),
            "url": f"{base}/",
            "logo": {"@type": "ImageObject", "url": f"{base}/logo-400.png"},
        },
    }
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{base}/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{base}/blog/"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": qa["question"].strip(),
             "acceptedAnswer": {"@type": "Answer", "text": qa["answer"].strip()}}
            for qa in payload["faq"]
        ],
    }
    builders = {"Article": article_ld, "BreadcrumbList": breadcrumb_ld, "FAQPage": faq_ld}
    seen: set[str] = set()

    def repl_ld(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        t = data.get("@type")
        if t in builders:
            seen.add(t)
            body = json.dumps(builders[t], ensure_ascii=False, indent=2)
            body = "\n".join("  " + line for line in body.splitlines())
            return ('<script type="application/ld+json">\n' + body +
                    '\n  </script>')
        return m.group(0)

    html = re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl_ld, html, flags=re.S)
    for needed in ("Article", "BreadcrumbList", "FAQPage"):
        if needed not in seen:
            raise Anchor(f"bloc JSON-LD « {needed} » absent du gabarit")

    # ---- fil d'Ariane visible ----
    html = sub1(r'(<li><a href="/blog/">Blog</a></li>\s*\n\s*<li>)(?:.*?)(</li>)',
                lambda m: m.group(1) + esc(title) + m.group(2), html, "fil d'Ariane", re.S)

    # ---- en-tête d'article ----
    html = sub1(r'(<span class="post-tag">)(?:.*?)(</span>)',
                lambda m: m.group(1) + esc(payload["category"].strip()) + m.group(2),
                html, "étiquette de catégorie", re.S)
    html = sub1(r"(<h1>)(?:.*?)(</h1>)",
                lambda m: m.group(1) + esc(title) + m.group(2), html, "h1", re.S)
    html = sub1(r'<time datetime="[^"]*">.*?</time>',
                lit(f'<time datetime="{iso}">{human}</time>'), html, "date", re.S)
    html = sub1(r"(<span>Lecture ~)\d+(\s*min</span>)",
                lambda m: m.group(1) + str(minutes) + m.group(2), html, "temps de lecture")
    html = sub1(r'(<img class="article-cover" src=")[^"]*(" alt=")[^"]*(")',
                lambda m: m.group(1) + cover + m.group(2) + esc(payload["image_alt"].strip()) + m.group(3),
                html, "image de couverture")
    html = sub1(r'(<p class="article-lede">)(?:.*?)(</p>)',
                lambda m: m.group(1) + esc(payload["lede"].strip()) + m.group(2),
                html, "chapô", re.S)

    # ---- corps ----
    body = format_body(payload["body_html"])
    # Les bornes sont cherchées À L'INTÉRIEUR de <article class="article">,
    # sinon le </header> du header de site servirait d'ancre et effacerait la page.
    art_m = re.search(r'<article class="article">', html)
    if not art_m:
        raise Anchor('conteneur <article class="article"> introuvable')
    offset = art_m.end()
    head_m = re.search(r"</header>", html[offset:])
    faq_m = re.search(r"<h2>Questions fréquentes</h2>", html[offset:])
    if not head_m or not faq_m or faq_m.start() < head_m.end():
        raise Anchor("bornes du corps introuvables (</header> … <h2>Questions fréquentes</h2>)")
    html = html[:offset + head_m.end()] + "\n\n" + body + "\n\n      " + html[offset + faq_m.start():]

    # ---- FAQ visible ----
    faq_html = "\n".join(
        "        <details>\n"
        f"          <summary>{esc(qa['question'].strip())}</summary>\n"
        f"          <p>{esc(qa['answer'].strip())}</p>\n"
        "        </details>"
        for qa in payload["faq"]
    )
    html = sub1(r'(<div class="faq">\n)(?:.*?)(\n\s*</div>\s*\n\s*<div class="article-cta">)',
                lambda m: m.group(1) + faq_html + m.group(2), html, "bloc FAQ", re.S)

    # ---- bloc CTA ----
    html = sub1(r'(<div class="article-cta">\s*\n\s*<h2>)(?:.*?)(</h2>)',
                lambda m: m.group(1) + esc(payload["cta_heading"].strip()) + m.group(2),
                html, "titre CTA", re.S)
    html = sub1(r'(<div class="article-cta">\s*\n\s*<h2>.*?</h2>\s*\n\s*<p>)(?:.*?)(</p>)',
                lambda m: m.group(1) + esc(payload["cta_text"].strip()) + m.group(2),
                html, "texte CTA", re.S)

    # ---- marqueur d'idempotence ----
    marker = f"<!-- {cfg['site_slug']}-topic: {topic['n']} -->"
    html = sub1(r"<body>", lit(f"<body>\n{marker}"), html, "balise body")

    return html


def format_body(raw: str) -> str:
    """Normalise l'indentation du corps généré (une balise de bloc par ligne)."""
    body = raw.strip()
    body = re.sub(r"</(h2|h3|p|ul|ol|div)>\s*", r"</\1>\n", body)
    body = re.sub(r"\s*<(h2|h3|p|ul|ol|div)(\s|>)", r"\n<\1\2", body)
    body = re.sub(r"\s*<li(\s|>)", r"\n  <li\1", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return "\n".join("      " + ln for ln in lines)


# ───────────────────────────── mises à jour annexes ─────────────────────────────

def update_blog_index(path: Path, cfg: dict, topic: dict, payload: dict,
                      now: datetime, cover: str) -> str:
    html = path.read_text(encoding="utf-8")
    url = f"/blog/{topic['slug']}/"
    if url in html:
        log("   · /blog/index.html contient déjà cet article — inchangé")
        return html

    iso = now.strftime("%Y-%m-%d")
    card = f"""          <article class="post-card">
            <a href="{url}" aria-label="Lire l'article : {esc(payload['title'].strip())}">
              <img src="{cover}" alt="{esc(payload['image_alt'].strip())}" loading="lazy" width="1200" height="675">
            </a>
            <div class="post-body">
              <span class="post-tag">{esc(payload['category'].strip())}</span>
              <h2><a href="{url}">{esc(payload['title'].strip())}</a></h2>
              <p class="post-meta"><time datetime="{iso}">{date_fr(now)}</time><span>·</span><span>Lecture ~{int(payload.get('reading_minutes') or 7)} min</span></p>
              <p>{esc(payload['meta_description'].strip())}</p>
              <a class="post-more" href="{url}">Lire l'article →</a>
            </div>
          </article>

"""
    html = sub1(r'(<div class="post-grid">\s*\n\n?)', lambda m: m.group(1) + card,
                html, "grille d'articles de /blog/index.html")

    # JSON-LD Blog : ajout en tête de blogPost
    def repl(m):
        data = json.loads(m.group(1))
        if data.get("@type") != "Blog":
            return m.group(0)
        posts = data.get("blogPost") or []
        posts.insert(0, {
            "@type": "BlogPosting",
            "headline": payload["title"].strip(),
            "url": f"{cfg['site_url']}{url}",
            "datePublished": iso,
        })
        data["blogPost"] = posts
        body = json.dumps(data, ensure_ascii=False, indent=2)
        body = "\n".join("  " + line for line in body.splitlines())
        return '<script type="application/ld+json">\n' + body + '\n  </script>'

    html = re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, html, flags=re.S)
    return html


def update_sitemap(path: Path, cfg: dict, topic: dict, now: datetime) -> str:
    xml = path.read_text(encoding="utf-8")
    loc = f"{cfg['site_url']}/blog/{topic['slug']}/"
    iso = now.strftime("%Y-%m-%d")
    if loc in xml:
        log("   · sitemap.xml contient déjà cette URL — inchangé")
        return xml

    # lastmod de /blog/
    xml = re.sub(rf"(<loc>{re.escape(cfg['site_url'])}/blog/</loc>\s*\n\s*<lastmod>)[^<]*(</lastmod>)",
                 lambda m: m.group(1) + iso + m.group(2), xml, count=1)

    entry = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{iso}</lastmod>\n"
             f"    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>\n")
    return sub1(r"</urlset>", lit(entry + "</urlset>"), xml, "fin de sitemap.xml")


def update_rss(path: Path, cfg: dict, topic: dict, payload: dict, now: datetime) -> str:
    xml = path.read_text(encoding="utf-8")
    link = f"{cfg['site_url']}/blog/{topic['slug']}/"
    if link in xml:
        log("   · rss.xml contient déjà cet article — inchangé")
        return xml

    pub = date_rfc822(now)
    xml = re.sub(r"(<lastBuildDate>)[^<]*(</lastBuildDate>)",
                 lambda m: m.group(1) + pub + m.group(2), xml, count=1)

    item = f"""
    <item>
      <title>{esc(payload['title'].strip())}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub}</pubDate>
      <category>{esc(payload['category'].strip())}</category>
      <description>{esc(payload['meta_description'].strip())}</description>
    </item>
"""
    return sub1(r'(<atom:link[^>]*/>\n)', lambda m: m.group(1) + item, xml, "flux RSS")


# ───────────────────────────── main ─────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Génère un article de blog et met à jour les index.")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit aucun fichier")
    ap.add_argument("--mock", action="store_true",
                    help="contenu de test sans appel réseau (implique --dry-run)")
    ap.add_argument("--topic", type=int, default=None, help="force le numéro de sujet")
    ap.add_argument("--config", default=str(ROOT / "blog-config.json"))
    args = ap.parse_args()

    if args.mock:
        args.dry_run = True

    started = time.time()
    now = datetime.now(timezone(timedelta(hours=2)))

    log("═" * 66)
    log("  Génération automatique d'article de blog")
    log(f"  {now.strftime('%Y-%m-%d %H:%M')} · mode : "
        f"{'MOCK (hors ligne)' if args.mock else ('DRY-RUN' if args.dry_run else 'ÉCRITURE')}")
    log("═" * 66)

    step("1. Configuration")
    cfg = load_config(Path(args.config))
    blog_dir = ROOT / cfg.get("blog_dir", "blog")
    workflow = ROOT / cfg.get("workflow_file", "BLOG_WORKFLOW.md")
    log(f"   site      : {cfg['site_name']}")
    log(f"   url       : {cfg['site_url']}")
    log(f"   marqueur  : <!-- {cfg['site_slug']}-topic: N -->")

    step("2. Sujets disponibles")
    topics = parse_topics(workflow)
    log(f"   {len(topics)} sujets listés dans {workflow.name}")

    step("3. Articles déjà publiés")
    slugs, markers = scan_existing(blog_dir, cfg["site_slug"])
    log(f"   {len(slugs)} article(s) en ligne : {', '.join(sorted(slugs)) or '—'}")
    log(f"   marqueurs de sujets traités : {sorted(markers) or '—'}")

    step("4. Sélection du sujet")
    topic = pick_topic(topics, slugs, markers, args.topic)
    log(f"   → sujet n°{topic['n']} : {topic['title']}")
    log(f"     slug : {topic['slug']}")

    target_dir = blog_dir / topic["slug"]
    target_file = target_dir / "index.html"
    if target_file.exists():
        die(f"/blog/{topic['slug']}/index.html existe déjà — arrêt sans modification "
            f"(idempotence)")

    step("5. Gabarit HTML")
    template, template_slug = load_template(cfg, blog_dir)
    if template_slug == topic["slug"]:
        die("le gabarit et l'article à générer sont le même fichier — arrêt")

    step("6. Rédaction")
    if args.mock:
        log("   mode --mock : aucun appel réseau, contenu de démonstration")
        payload = mock_payload(cfg, topic)
    else:
        payload = call_openai(cfg, topic, extract_editorial_rules(workflow))
    log(f"   titre    : {payload.get('title', '?')}")
    log(f"   longueur : {word_count(payload.get('body_html', ''))} mots (corps)")

    step("7. Validation éditoriale")
    try:
        warnings = validate(payload, cfg)
    except ValueError as e:
        die(f"contenu refusé — {e}")
    for w in warnings:
        log(f"   ⚠ {w}")
    if not warnings:
        log("   aucun avertissement")

    step("8. Assemblage HTML")
    covers = [c for c in cfg.get("cover_images", []) if (ROOT / c.lstrip("/")).exists()]
    if not covers:
        die("aucune image de couverture valide dans blog-config.json « cover_images »")
    cover = covers[(topic["n"] - 1) % len(covers)]
    log(f"   image de couverture : {cover}")
    try:
        article_html = build_article_html(template, cfg, topic, payload, now, cover)
        index_html = update_blog_index(blog_dir / "index.html", cfg, topic, payload, now, cover)
        sitemap_xml = update_sitemap(ROOT / cfg.get("sitemap_file", "sitemap.xml"), cfg, topic, now)
        rss_xml = update_rss(ROOT / cfg.get("rss_file", "rss.xml"), cfg, topic, payload, now)
    except Anchor as e:
        die(f"gabarit non conforme — {e}\n"
            f"  Le format de /blog/{template_slug}/index.html a changé : "
            f"réaligner le script ou l'article de référence.")

    # contrôles finaux sur le HTML produit
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                            article_html, re.S):
        try:
            json.loads(block)
        except json.JSONDecodeError as e:
            die(f"JSON-LD invalide dans l'article généré : {e}")
    if article_html.count("<h1>") != 1:
        die("l'article généré ne contient pas exactement un <h1>")
    log(f"   article assemblé : {word_count(article_html)} mots au total")

    step("9. Écriture")
    if args.dry_run:
        log("   dry-run : aucun fichier écrit.")
        log("\n" + "─" * 66)
        log("APERÇU — titre : " + payload["title"].strip())
        preview = " ".join(strip_tags(payload["body_html"]).split())
        log("APERÇU — corps :\n" + preview[:1200] + ("…" if len(preview) > 1200 else ""))
        log("─" * 66)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(article_html, encoding="utf-8")
        (blog_dir / "index.html").write_text(index_html, encoding="utf-8")
        (ROOT / cfg.get("sitemap_file", "sitemap.xml")).write_text(sitemap_xml, encoding="utf-8")
        (ROOT / cfg.get("rss_file", "rss.xml")).write_text(rss_xml, encoding="utf-8")
        log(f"   écrit : /blog/{topic['slug']}/index.html")
        log("   mis à jour : /blog/index.html, sitemap.xml, rss.xml")

    log(f"\n✔ Terminé en {time.time() - started:.1f}s — sujet n°{topic['n']} « {topic['title']} »")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log("\n✖ Interrompu.")
        sys.exit(EXIT_ERROR)
    except Exception as exc:                        # noqa: BLE001 — filet de sécurité
        log(f"\n✖ ERREUR inattendue : {type(exc).__name__}: {exc}")
        sys.exit(EXIT_ERROR)
