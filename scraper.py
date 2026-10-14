"""Scrapea vacantes de auxiliar administrativa / capturista en Monterrey y las sirve en una página simple."""

import json
import os
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs

PUBLIC = Path(__file__).parent / "public"
DATA = PUBLIC / "data" / "jobs.json"

SEARCH_TERMS = [t.strip() for t in os.getenv("SEARCH_TERMS", "auxiliar administrativo,auxiliar administrativa,capturista,asistente administrativa").split(",")]
LOCATION = os.getenv("LOCATION", "Monterrey, Nuevo León")
HOURS_OLD = int(os.getenv("HOURS_OLD", "72"))
RESULTS = int(os.getenv("RESULTS", "40"))
EVERY_HOURS = float(os.getenv("EVERY_HOURS", "6"))
KEEP_DAYS = int(os.getenv("KEEP_DAYS", "21"))

# Si el título no tiene ninguna de estas, se descarta (LinkedIn devuelve mucha basura).
TITLE_KEYWORDS = ("auxiliar", "capturista", "captura", "administrativ", "asistente", "recepcion", "oficina")
FIELDS = ("title", "company", "location", "job_url", "site", "description", "date_posted", "job_type", "min_amount", "max_amount", "interval", "currency")


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_relevant(title) -> bool:
    return any(k in norm(title) for k in TITLE_KEYWORDS)


def clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return value


def load() -> dict:
    try:
        return {j["job_url"]: j for j in json.loads(DATA.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def scrape_once():
    jobs = load()
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    new = 0
    for term in SEARCH_TERMS:
        try:
            df = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=term,
                location=LOCATION,
                results_wanted=RESULTS,
                hours_old=HOURS_OLD,
                country_indeed="Mexico",
                fetch_description=True,
            )
        except Exception as exc:  # un sitio caído no debe tumbar el resto
            print(f"[{term}] error: {exc}", flush=True)
            continue
        for rec in df.to_dict(orient="records"):
            job = {k: clean(rec.get(k)) for k in FIELDS}
            url = job["job_url"]
            if not url or not is_relevant(job["title"]):
                continue
            if url not in jobs:
                new += 1
                job["first_seen"] = now
            else:
                job["first_seen"] = jobs[url]["first_seen"]
            jobs[url] = job

    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    kept = sorted(
        (j for j in jobs.values() if j["first_seen"] >= cutoff),
        key=lambda j: (j.get("date_posted") or j["first_seen"][:10], j["first_seen"]),
        reverse=True,
    )
    DATA.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DATA)
    (DATA.parent / "meta.json").write_text(json.dumps({"updated": now}), encoding="utf-8")
    print(f"{now}: {new} nuevas, {len(kept)} en total", flush=True)


def loop():
    while True:
        scrape_once()
        time.sleep(EVERY_HOURS * 3600)


if __name__ == "__main__":
    assert is_relevant("Auxiliar Administrativa") and is_relevant("CAPTURISTA de datos") and is_relevant("Asistente Administrativo")
    assert not is_relevant("Vendedor de piso")
    threading.Thread(target=loop, daemon=True).start()
    handler = partial(SimpleHTTPRequestHandler, directory=str(PUBLIC))
    print("Sirviendo en http://localhost:8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), handler).serve_forever()
