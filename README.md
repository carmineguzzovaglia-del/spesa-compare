# Spesa Compare Tool - MVP reale

Questo è un MVP locale per confrontare prezzi online partendo da una lista spesa.

## Cosa fa
- Inserisci una lista prodotti.
- Cerca online sui siti configurati.
- Prova a estrarre nome prodotto, prezzo e link.
- Calcola il negozio migliore per ogni prodotto.
- Esporta CSV con i risultati.

## Limite onesto
I siti dei supermercati cambiano spesso, possono richiedere CAP/località/login o bloccare automazioni.
Questo tool usa Playwright in modalità browser reale, quindi è più robusto di un semplice scraper HTML, ma non garantisce il 100% dei risultati.

## Installazione

1. Installa Python 3.10+
2. Apri il terminale nella cartella del progetto
3. Esegui:

```bash
pip install -r requirements.txt
playwright install chromium
```

## Avvio

```bash
streamlit run app.py
```

Poi apri il link che Streamlit mostra nel browser.

## Come usarlo
1. Inserisci i prodotti, uno per riga.
2. Premi "Cerca prezzi online".
3. Controlla la tabella.
4. Esporta CSV.

## Supermercati configurati
- Carrefour
- Esselunga
- CoopShop

Lidl/Eurospin sono più difficili perché spesso non espongono un catalogo spesa completo consultabile come ecommerce.