# Regola permanente: test di regressione MiniFiles

Decisione di Michele del 30 ottobre 2026. Questa regola vale per l'applicazione MiniFiles, la landing e i relativi strumenti locali. Va letta prima di creare, modificare o eseguire test. Sostituisce le precedenti richieste di test UI e verifiche browser automatiche.

- Conservare e aggiungere soltanto regressioni di logica applicativa: backend, API e loro contratti, query e persistenza, migrazioni, autenticazione, autorizzazioni, validazione, filesystem, concorrenza, trasferimenti, coda, selezione e filtraggio dei file, calcoli e aggiornamento dei dati statistici.
- Non creare, mantenere o eseguire test UI: rendering Vue/SSR, mount di componenti, HTML/DOM, selettori, classi CSS, testi o etichette dell'interfaccia, attributi accessibili, screenshot o confronti visivi, geometria, layout, animazioni o sequenze della demo. Questo vale anche per test di funzioni pure quando verificano esclusivamente la presentazione.
- Nessun runner Playwright, Puppeteer o browser headless per regressioni UI, né harness o suite end-to-end che verificano la presentazione. Le precedenti autorizzazioni al loro uso non impongono di ripristinarli.
- I test TypeScript di logica restano consentiti in Node, senza renderizzare componenti o introdurre un ambiente DOM. Mock di File, richieste HTTP/XHR e dati del filesystem servono a verificare algoritmi e transizioni applicative, non l'interfaccia.
- Nei test misti rimuovere le asserzioni UI e conservare quelle sui comportamenti applicativi. Sono consentiti controlli sui payload delle API e sulla propagazione degli errori; non vincolare le etichette prodotte per l'interfaccia. Uno snapshot di dati statistici non è uno snapshot visuale.
- Typecheck, lint, formattazione, build e smoke test HTTP/API o di persistenza rimangono consentiti. Eseguirli quando pertinenti alle modifiche, senza introdurre test UI sostitutivi.
- I vecchi report e screenshot sono evidenze storiche: non rappresentano suite da ripristinare o verifiche UI obbligatorie. Una futura modifica di questa regola richiede una nuova istruzione esplicita di Michele.
