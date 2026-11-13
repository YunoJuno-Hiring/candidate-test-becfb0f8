FROM node:24-slim

WORKDIR /app

# pnpm via corepack, at the version pinned in package.json's packageManager.
# pnpm doesn't run dependency install scripts unless allowed, which is the
# project's reason for using it over npm (see flake.nix).
RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

COPY index.js .

# The official Node images ship an unprivileged "node" user; don't run as root.
USER node

EXPOSE 8027

CMD ["node", "index.js"]
