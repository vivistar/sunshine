# Sunshine — Front End

A small Vite + React single-page app: a daily affirmation plus live weather for
Brownsburg, IN and Chicago, IL (via the [Open-Meteo](https://open-meteo.com/)
API). It also links out to the Sunshine **survey & conjoint tool** that lives in
the [`app/`](../app) directory of this repository.

## Develop

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

## Build

```bash
npm run build    # outputs static assets to frontend/dist
npm run preview  # preview the production build locally
```

## Linking to the survey tool

The header ("Survey Tool →") and footer both link to the survey tool. The target
URL is read from the `VITE_SURVEY_URL` build-time environment variable and
defaults to `/` (the survey tool's home), which works when both apps are served
from the same origin.

When the survey tool is deployed separately, point the front end at it:

```bash
# frontend/.env (see .env.example)
VITE_SURVEY_URL=https://surveys.example.com/
```

Vite only exposes env vars prefixed with `VITE_` to client code.
