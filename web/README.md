# File Memory web frontend

This is a dependency-free, vanilla HTML/CSS/JavaScript frontend for the local-first File Memory app. It can be served as static files by the backend (or any static file server) and does not download fonts, images, or scripts from the network. The Inbox provides local search and safe open/forget actions; Settings controls folders, pause state, AI mode, ignored extensions, and index rebuilding.

## Run locally

From the project root, serve this folder with any local static server, for example:

```bash
python -m http.server 8080 --directory web
```

Open <http://127.0.0.1:8080/>. The page expects the HTTP API on the same origin. The recommended command is `python -m filememory.web`, which serves both the page and API on loopback. To use another local API origin, set `window.FILE_MEMORY_API_BASE` before `app.js` loads.

## API calls

The UI uses these endpoints when available:

- `GET /api/search?q=...&semantic=true|false`
- `GET /api/folders`
- `GET /api/settings`
- `POST /api/folders` with `{ "path": "..." }`
- `DELETE /api/folders?path=...&confirmed=true`
- `POST /api/settings` with pause, AI mode, and ignored extensions
- `POST /api/rebuild`
- `POST /api/files/forget` with `{ "path": "...", "confirmed": true }`
- `POST /api/actions/open-file` with `{ "path": "..." }`
- `POST /api/actions/open-folder` with `{ "path": "..." }`

Search results may be a JSON array or an object containing `results`, `matches`, `items`, or `data`. Errors are shown as errors; the frontend never invents result or action success data.
