import asyncio
import re
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

@dataclass
class SearchResult:
    store: str
    query: str
    title: str
    price: float | None
    price_text: str
    url: str
    confidence: str

STORES = {
    "Carrefour": {
        "search_urls": [
            "https://www.carrefour.it/search?q={query}",
            "https://www.carrefour.it/spesa-online/search?q={query}",
        ],
        "domain": "carrefour.it",
    },
    "Esselunga": {
        "search_urls": [
            "https://spesaonline.esselunga.it/commerce/nav/supermercato/store/search/{query}",
            "https://spesaonline.esselunga.it/commerce/nav/supermercato/store/home?search={query}",
        ],
        "domain": "esselunga.it",
    },
    "CoopShop": {
        "search_urls": [
            "https://www.coopshop.it/search?q={query}",
            "https://www.coopshop.it/catalogsearch/result/?q={query}",
        ],
        "domain": "coopshop.it",
    },
}

PRICE_RE = re.compile(r"(?:€|EUR)?\s*([0-9]{1,3}(?:[.,][0-9]{2}))\s*(?:€|EUR)?")

def parse_price(text: str) -> tuple[float | None, str]:
    if not text:
        return None, ""
    candidates = []
    for match in PRICE_RE.finditer(text):
        raw = match.group(1)
        try:
            val = float(raw.replace(",", "."))
            if 0.05 <= val <= 300:
                candidates.append((val, match.group(0).strip()))
        except ValueError:
            pass
    if not candidates:
        return None, ""
    # prefer small plausible item price
    candidates.sort(key=lambda x: x[0])
    return candidates[0]

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

async def search_store(playwright, store_name: str, query: str, max_results: int = 5) -> list[SearchResult]:
    cfg = STORES[store_name]
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        viewport={"width": 1366, "height": 900},
    )

    results: list[SearchResult] = []
    encoded = quote_plus(query)

    for url_tpl in cfg["search_urls"]:
        url = url_tpl.format(query=encoded)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3500)

            # Try cookie buttons
            for label in ["Accetta", "Accetto", "Accept", "OK", "Va bene", "Continua"]:
                try:
                    btn = page.get_by_text(label, exact=False).first
                    if await btn.count() > 0:
                        await btn.click(timeout=1500)
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            html = await page.content()
            text = clean_text(await page.locator("body").inner_text(timeout=5000))

            # Generic product-card extraction from visible links and nearby text.
            links = await page.locator("a").evaluate_all("""
                els => els.slice(0,250).map(a => ({
                    text: (a.innerText || a.textContent || '').trim(),
                    href: a.href || ''
                })).filter(x => x.text && x.href)
            """)

            seen = set()
            for link in links:
                title = clean_text(link.get("text", ""))
                href = link.get("href", "")
                if not href or cfg["domain"] not in href:
                    continue

                lower_title = title.lower()
                if len(title) < 3 or any(bad in lower_title for bad in ["privacy", "login", "registrati", "carrello", "servizi", "newsletter"]):
                    continue

                # title relevance: at least one word from query
                qwords = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
                if qwords and not any(w in lower_title for w in qwords):
                    continue

                key = (title[:80], href.split("?")[0])
                if key in seen:
                    continue
                seen.add(key)

                idx = text.lower().find(title.lower()[:40])
                nearby = text[idx:idx+700] if idx >= 0 else title
                price, price_text = parse_price(nearby)

                if price is not None:
                    results.append(SearchResult(
                        store=store_name,
                        query=query,
                        title=title[:160],
                        price=price,
                        price_text=price_text,
                        url=href,
                        confidence="media"
                    ))

                if len(results) >= max_results:
                    break

            # Fallback: if visible page has prices but no links, capture generic price.
            if not results:
                price, price_text = parse_price(text[:5000])
                if price is not None:
                    results.append(SearchResult(
                        store=store_name,
                        query=query,
                        title=f"Risultato generico per {query}",
                        price=price,
                        price_text=price_text,
                        url=url,
                        confidence="bassa"
                    ))

            if results:
                break

        except PlaywrightTimeoutError:
            continue
        except Exception as e:
            results.append(SearchResult(
                store=store_name,
                query=query,
                title=f"Errore ricerca: {type(e).__name__}",
                price=None,
                price_text="",
                url=url,
                confidence="errore"
            ))

    await browser.close()
    return results

async def search_all(products: list[str], selected_stores: list[str]) -> pd.DataFrame:
    rows = []
    async with async_playwright() as p:
        for product in products:
            for store in selected_stores:
                found = await search_store(p, store, product)
                if found:
                    rows.extend([asdict(x) for x in found])
                else:
                    rows.append(asdict(SearchResult(
                        store=store,
                        query=product,
                        title="Nessun risultato trovato",
                        price=None,
                        price_text="",
                        url="",
                        confidence="nessuno"
                    )))
    return pd.DataFrame(rows)

def build_best_table(df: pd.DataFrame) -> pd.DataFrame:
    valid = df.dropna(subset=["price"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["query", "best_store", "title", "price", "url"])
    idx = valid.groupby("query")["price"].idxmin()
    best = valid.loc[idx, ["query", "store", "title", "price", "url", "confidence"]]
    return best.rename(columns={"store": "best_store"}).sort_values("query")

st.set_page_config(page_title="Confronto Spesa", layout="wide")

st.title("Confronto Spesa Online")
st.caption("MVP reale: cerca prezzi online con Playwright. Funziona meglio su siti con catalogo pubblico e può fallire se servono CAP, login o anti-bot.")

default_list = "pasta\nriso basmati\ntonno\npollo\nyogurt greco\nuova\npiadine\nzucchine\npomodorini"

products_text = st.text_area("Lista prodotti, uno per riga", default_list, height=220)
selected_stores = st.multiselect("Supermercati", list(STORES.keys()), default=["Carrefour", "Esselunga", "CoopShop"])
run = st.button("Cerca prezzi online", type="primary")

if run:
    products = [x.strip() for x in products_text.splitlines() if x.strip()]
    if not products:
        st.error("Inserisci almeno un prodotto.")
    elif not selected_stores:
        st.error("Seleziona almeno un supermercato.")
    else:
        with st.spinner("Cerco online. Potrebbe metterci qualche minuto..."):
            df = asyncio.run(search_all(products, selected_stores))

        st.subheader("Risultati grezzi")
        st.dataframe(df, use_container_width=True)

        st.subheader("Miglior prezzo per prodotto")
        best = build_best_table(df)
        st.dataframe(best, use_container_width=True)

        total = best["price"].sum() if not best.empty else 0
        st.metric("Totale stimato comprando dove costa meno", f"{total:.2f} €")

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Scarica risultati CSV", csv, "risultati_spesa.csv", "text/csv")

        st.warning("Controlla sempre formato e quantità: un prezzo basso può riferirsi a confezioni diverse. La versione successiva deve normalizzare €/kg o €/L.")