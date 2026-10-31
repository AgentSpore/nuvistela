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

## Docker

```bash
docker build -t bumbli-frontend .
docker run --rm -p 3000:3000 bumbli-frontend   # PORT env overrides 3000
```

The image pins `HOSTNAME=0.0.0.0`; do not run it with `-e HOSTNAME=127.0.0.1` (every default-locale page would loop on 307, the server exits at boot).

`NEXT_PUBLIC_API_URL` and `API_ORIGIN` are inlined at build time: pass `--build-arg`. Without `API_ORIGIN` the image expects a reverse proxy to serve `/api` (the real deploy in K5 uses Caddy); `docker compose` passes `API_ORIGIN=http://backend:8080`.
