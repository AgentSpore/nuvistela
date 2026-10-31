# Bumbli frontend

Next.js 16 (App Router), React 19, Tailwind 4, next-intl (ru default, en at `/en`).

## Commands

```bash
pnpm install
pnpm dev                     # http://localhost:3000
pnpm tsc --noEmit && pnpm lint && pnpm test
pnpm build
```

`NEXT_PUBLIC_API_URL` sets the API base URL (default `http://localhost:8080/api/v1`, see `.env.example`).

## Docker

```bash
docker build -t bumbli-frontend .
docker run --rm -p 3000:3000 bumbli-frontend   # PORT env overrides 3000
```

`NEXT_PUBLIC_API_URL` is inlined at build time: pass `--build-arg NEXT_PUBLIC_API_URL=...`.
