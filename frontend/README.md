# Bumbli frontend

Next.js 16 (App Router), React 19, Tailwind 4, next-intl (ru default, en at `/en`).

## Commands

```bash
pnpm install
pnpm dev                     # http://localhost:3000
pnpm tsc --noEmit && pnpm lint && pnpm test
pnpm build
```

`NEXT_PUBLIC_API_URL` sets the API base URL (default relative `/api/v1`, so the browser stays on one origin).
`API_ORIGIN` (e.g. `http://localhost:8080`) makes Next rewrite `/api/*` to the backend; set it for `pnpm dev` and `pnpm build`. See `.env.example`.
The public card page `/{locale}/w/{token}` also reads `API_ORIGIN` at runtime, on the server, to fetch the card (default `http://127.0.0.1:8080` when unset); in a container set it as a runtime env var (`docker run -e`, compose `environment`), else the page cannot reach the backend and answers 500. The absolute `og:image` origin comes from `x-forwarded-host`/`host` and `x-forwarded-proto`, so the reverse proxy must pass them.

## Docker

```bash
docker build -t bumbli-frontend .
docker run --rm -p 3000:3000 bumbli-frontend   # PORT env overrides 3000
```

The image pins `HOSTNAME=0.0.0.0`; do not run it with `-e HOSTNAME=127.0.0.1` (every default-locale page would loop on 307, the server exits at boot).

`NEXT_PUBLIC_API_URL` and the `/api` rewrite target `API_ORIGIN` are inlined at build time: pass `--build-arg`. The share-card page also needs `API_ORIGIN` at runtime (`-e API_ORIGIN=...`); `docker compose` sets both. Without `API_ORIGIN` the image expects a reverse proxy to serve `/api` (the real deploy in K5 uses Caddy); `docker compose` passes `API_ORIGIN=http://backend:8080`.

## 3D worlds

The world card offers a walk-through for genres listed in `src/lib/world-3d-assets.ts` (`space` has none). Three.js and Spark are imported only after the tap (`src/lib/world-3d-viewer.ts`); the page never loads them. Assets live in `public/worlds/<id>/` with a content hash in the file name and are served `immutable` (`next.config.ts`). To change an asset, add a new hashed file and update the table. The panorama replaces the viewer when WebGL2 is missing or fails; `?nogl` forces it.
