# Genesis round — phase decomposition

*Round identifier : `2026-05-genesis`*
*Source code : `augure/predictor/` (kalshi-poc imported 2026-05-08)*
*Decomposition date : 2026-05-08*
*Method : agent reads actual source files and groups them into logical phases.*

## Méthode

Le repo `predictor/` n'a pas d'historique granulaire de PRs (kalshi-poc était un dossier non versionné, importé en commit unique). La décomposition logique se fait sur la base des **modules livrés et fonctionnels** observables dans l'arborescence finale. Chaque phase regroupe un ensemble cohérent de fichiers, dépendances et tests qui forment une livraison fonctionnelle indépendante.

Cette décomposition est l'input de l'agent de valuation pour le round genesis.

---

## Phase 0 — Setup, design et stratégie

**Artefacts observables**
- `predictor/README.md` (92 lignes) : description vision, architecture en ASCII, pipeline d'exécution, état actuel checklist, "Ce qu'on NE fait PAS" explicite (pas de smart contract, pas d'argent réel)
- `predictor/requirements.txt` (5 deps : requests, pandas, numpy, dateutil, tabulate)
- `predictor/src/config.py` (33 lignes) : chemins, base API, paramètres simulation (Kelly fractionnel 25 %, edge minimum 5 %, max position 5 % bankroll, starting bankroll $1000)
- Document de stratégie identifiant 5 angles d'edge (méta-ensemble IA, NWS resolution, microstructure, crowdsourced, soil moisture/MJO) — visible dans la mémoire projet
- Décision motivée NE PAS répliquer LightGBM mainstream

**Profil dominant** : researcher quant (choix méthodologiques) + senior dev (setup technique)

---

## Phase 1 — Client Kalshi (lecture publique)

**Artefacts observables**
- `predictor/src/kalshi/client.py` (128 lignes) : KalshiClient avec session HTTP, pagination cursor-based, retries 429 avec backoff exponentiel, filtre catégorie + mots-clés titre, méthodes list_series / list_weather_series / list_events / get_event / get_market / get_orderbook / snapshot_event
- `predictor/src/kalshi/models.py` (132 lignes) : dataclasses Series / Market / Event, gestion explicite du dual format API (cents int legacy + dollars string), fonctions `_price_to_dollars()` et `_to_float()` robustes

**Profil dominant** : senior dev backend

---

## Phase 2 — Intégration Open-Meteo (forecast + historique)

**Artefacts observables**
- `predictor/src/weather/open_meteo.py` (420 lignes)
  - 11 villes mappées avec coordonnées et timezone NWS-aligned (CITIES dict)
  - 5 modèles confirmés Open-Meteo (AVAILABLE_MODELS) : ecmwf_ifs025, ecmwf_aifs025_single (AI), gfs_graphcast025 (DeepMind), gfs_global, jma_gsm
  - Dataclasses DailyObservation + DailyForecast avec properties de conversion mm→inches, cm→inches
  - Endpoints forecast() (déterministe), forecast_ensemble() (GFS GEFS members), forecast_multi_model() (parsing post-fixe modèle), historical() + historical_observations() (ERA5)
  - Cache disque avec garde-fou `_has_usable_series()` (fix de Phase A.1-bugfix, voir plus bas)
  - Helper `_parse_multi_model_daily()` pour gérer le suffix `_<model>` Open-Meteo

**Profil dominant** : ML/data engineer

---

## Phase 3 — Predictors core (climatologie + forecast_blend)

**Artefacts observables**
- `predictor/src/predictors/base.py` (73 lignes) : interface abstraite Predictor + dataclasses ContractSpec / Prediction, type Literal pour WeatherVar
- `predictor/src/predictors/parsers.py` (143 lignes) : SERIES_MAP (22 entries series_prefix → variable + city), parse_kalshi_date (26MAY08 → 2026-05-08), 7 patterns regex pour subtitles ("75° or below", "76° to 77°", "1.0\" to 2.0\"", etc.), parse_market wrapper
- `predictor/src/predictors/climatology.py` (131 lignes) : ClimatologyPredictor avec fenêtre saisonnière ±3j, Laplace smoothing 0.5, arrondi NWS pour temp, confidence basée sur n_obs, fallback 0.5 si pas de données
- `predictor/src/predictors/forecast_blend.py` (161 lignes) : ForecastBlendPredictor combinant forecast Open-Meteo (mu) + sigma climato, CDF normale `_normal_cdf`, blend horizon `exp(-d/8)`, gestion cas dégénérés (out_of_range, error → fallback climato)

**Profil dominant** : researcher quant (math probabiliste + domain météo)

---

## Phase 4 — Simulation paper-trading

**Artefacts observables**
- `predictor/src/simulation/sizing.py` (45 lignes) : Kelly fractionnel (25 % par défaut), gestion YES/NO symétrique, clamping prob [1e-6, 1-1e-6] et px [0.01, 0.99], cap `max_fraction_per_bet`
- `predictor/src/simulation/ledger.py` (88 lignes) : dataclass PaperBet avec champs résolution, Ledger CSV append-only avec read_all / write_all, cast types depuis CSV (CSV étant string)

**Profil dominant** : senior dev backend

---

## Phase 5 — Backtest scoring infrastructure

**Artefacts observables**
- `predictor/src/simulation/scoring.py` (76 lignes) : brier_score, log_loss avec eps clamp, aggregate_metrics avec base_rate + brier baseline constant + Brier skill score, event_top1_accuracy pour mutually exclusive events
- `predictor/scripts/backtest.py` (176 lignes) : args CLI riches (--series, --predictor, --limit, --years-back), garde-fou `predictor=climatology` pour backtest historique (pas forecast_blend/ensemble qui appellent un forecast actuel = leakage), normalisation events mutuellement exclusifs, top-1 accuracy, breakdown per-series, JSON output

**Profil dominant** : ML engineer

**Premier résultat baseline empirique** (mémoire projet) : climato pure sur 16 events Austin → top-1 31 %, Brier skill score −0,21. Confirme la nécessité de NWP+ML.

---

## Phase B-1 — Résolution administrative NWS

**Artefacts observables**
- `predictor/src/kalshi/resolution.py` (394 lignes) :
  - Catalogue de **18 stations NWS** avec cli_code + ICAO + lat/lon + wfo (NWS_STATIONS dict)
  - Mapping series_prefix → station (40 entries SERIES_TO_STATION) avec conventions Kalshi internes (TLV = Las Vegas pas Tel Aviv, KXRAINCHIM = Midway pas O'Hare)
  - Inference variable depuis préfixe série (KXHIGHT > KXHIGH ordering pour matcher KXHIGHTLV)
  - Extraction station depuis `rules_primary` avec **3 patterns regex** (CLI explicite > pattern textuel structuré > nom dans le texte) + fallback série
  - 24 mappings nom textuel → station (`_NAME_TO_STATION`)
  - Apply NWS rounding **round-half-up** explicite (75.5 → 76, distinct du banker's rounding Python qui ferait 76)
  - Verdict déterministe `would_resolve_yes` avec gestion strike_type less / greater / between
  - Convention Trace = YES pour rain seuil 0 (avec garde-fou : seulement seuil ≤ 0)
  - `near_threshold_margin` pour identifier les knife-edge markets
- `predictor/scripts/audit_resolution.py` : scan tous les snapshots, rapport stations + cas-limites (lu indirectement)
- `predictor/scripts/test_resolution.py` (198 lignes) : **9 tests** asserts couvrant rounding temp + precip, infer_variable, extract_station 3 cas (Austin / NYC / Midway), résolution Austin T76 (less, knife-edge à 75.5), Austin B76.5 (between bornes inclusives sur arrondi), Austin T83 (greater seuil exclusif), Rain NYC trace (seuil 0 → trace=YES), Rain Chicago >1″ (trace ne court-circuite pas seuil non-zero)

**Profil dominant** : researcher quant (domain knowledge NWS Surface Observation Manual)

---

## Phase B-2 — Analyse microstructure Kalshi

**Artefacts observables**
- `predictor/src/microstructure/distribution.py` (119 lignes) : dataclass BinQuote avec yes_mid, spread, midpoint adapté au strike_type ; fonctions extract_bins (sort par midpoint), sum_yes_mid, implied_distribution normalisée (somme 1), implied_mean_std
- `predictor/src/microstructure/biases.py` (188 lignes) : dataclass EventBiases avec n_bins, vig_residual, median/extreme/central spreads, spread_skew, implied mean/std, modal_oi_share, tail_mass, notes auto-générées ; fonction `tail_underpricing_vs_climato()` pour comparer probas implicites Kalshi à climato par bin extrême
- `predictor/scripts/analyze_microstructure.py` : rapport texte + JSON par event (lu indirectement)
- `predictor/scripts/test_microstructure.py` (125 lignes) : **6 tests** asserts couvrant extract_bins ordering Austin (6 bins), sum_yes_mid (vig dans plage 0.7-1.6), implied_distribution normalisée, implied_mean_std plausibilité (Austin mai → 70-95°F, std 0-15°F), event_biases full Austin (vig + spread médian + skew calculés), event_biases singleton Rain NYC (1 bin, pas de skew)

**Profil dominant** : researcher quant

**Résultat empirique** (mémoire projet) : audit 32 events temp mutex → vig moyenne payée au mid +0,16 % (Kalshi très efficient), 29/32 events ont des bins extrêmes plus serrés que le centre — **hypothèse "tail underpricing structurel" rejetée**.

---

## Phase A.1 — Méta-ensemble IA + pipeline forward-test

**Artefacts observables**
- `predictor/src/predictors/ensemble.py` (213 lignes) : EnsemblePredictor avec mode uniform + hook poids customs, validation modèles inconnus, sigma_inter (epistémique = std des modèles) + sigma_climato (résiduel) en quadrature `sigma_total = sqrt(sigma_inter² + (0.5 × sigma_climato)²)`, correction arrondi NWS ±0.5°F sur les bornes, blend horizon `exp(-days_ahead / 8.0)` vers climato, fallback climato si out_of_horizon ou no_model_returned_value
- Extension `predictor/src/weather/open_meteo.py` (~50 lignes ajoutées) : `forecast_multi_model()` + AVAILABLE_MODELS + DEFAULT_ENSEMBLE + `_parse_multi_model_daily()`
- `predictor/scripts/test_ensemble.py` (80 lignes) : table comparative live mkt_mid vs climato vs blend vs ensemble + sigma_inter + mu (check de plausibilité)
- `predictor/scripts/forward_predict.py` (148 lignes) : capture quotidienne avec args CLI (--predictors, --series), filtrage série, snapshot horodaté JSON `data/predictions/forward_<TS>.json`, extraction inputs slimés
- `predictor/scripts/score_forward.py` (192 lignes) : charge captures, dédup par ticker (PREMIÈRE prédiction = la plus tôt avant résolution, anti-leakage), fetch résolutions Kalshi, aggregate metrics par predictor + comparaison **vs kalshi_mid** (référence ultime), JSON output dans `data/scores/`

**Profils dominants** (décomposition selon nature) :
- ML/data engineer : extension multi-modèle Open-Meteo, ~6h
- Researcher quant : logique d'ensemble, propagation sigma, blend horizon, ~12h
- Senior dev backend : forward_predict + score_forward + intégration Kalshi pour résolutions, ~10h

---

## Phase A.1-bugfix — Stabilisation runtime

**Artefacts observables**
- Garde-fou `_has_usable_series()` dans `cached_or_fetch` de `open_meteo.py` (lignes 396-411) : refuse d'écrire un cache vide, supprime cache vide existant. Évite le piège "0 obs cachés à vie" sur réponse Open-Meteo silencieusement vide
- Fonction `_price_to_dollars()` dans `kalshi/models.py` : auto-détection format `<base>_dollars` (string décimal) vs `<base>` (cents int legacy), normalisation en floats [0.0, 1.0]
- `predictor/scripts/simulate.py` : correction division /2.0 (anciennement /200 héritage cents → dollars)

**Profil dominant** : senior dev backend

**Pourquoi compté en phase distincte** : ces fixes ont émergé en runtime après le code initial. Justifie un coefficient qualité explicite (positif parce que régressions prévenues par garde-fous structurels, pas patches superficiels).

---

## Phase Daily Run — orchestrateur opérationnel

**Artefacts observables**
- `predictor/scripts/daily_run.py` (84 lignes) : routine quotidienne idempotente fetch_markets → forward_predict → score_forward, timeouts 30 min par step, traceback sur exception, exit code agrégé, trace stdout structurée pour debug

**Profil dominant** : senior dev

**Pourquoi compté à part** : l'orchestrateur n'est pas un module métier mais un assemblage qui rend le forward-test régulier opérationnellement viable. Permet la collecte continue requise pour le critère N>50 events résolus.

---

## Hors-scope du round genesis

Les artefacts suivants sont produits par JS mais **ne rentrent pas dans cette valuation** car ils relèvent du repo `augure/rounds/`, `augure/contracts/`, `augure/docs/` (méta-design du système d'émission, pas de code prédiction) :

- Conception du modèle de tokens AUG-POC (`docs/token_model.md`, `docs/value_engine.md`)
- Création du repo public `augure-rounds` puis monorepo `augure` (RUBRIC, HOURLY_RATES, PROMPT bilingues, scripts)
- Architecture monorepo (rounds/, contracts/, predictor/, docs/)

Ces artefacts feront l'objet d'un round séparé `2026-05-augure-rounds-genesis` ou seront intégrés au premier round mensuel régulier `2026-06`. Décision à trancher avec JS.
