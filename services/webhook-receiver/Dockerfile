FROM node:20-slim

WORKDIR /app

# pnpm via corepack, at the version pinned in package.json's packageManager.
# pnpm doesn't run dependency install scripts unless allowed, which is the
# project's reason for using it over npm (see flake.nix).
RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

COPY index.js .

EXPOSE 8027

CMD ["node", "index.js"]
