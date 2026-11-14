FROM node:24-slim

WORKDIR /app

# pnpm (pinned via packageManager) won't run dependency install scripts: the project's no-npm reason.
RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

COPY index.js .

# The official Node images ship an unprivileged "node" user; don't run as root.
USER node

EXPOSE 8027

CMD ["node", "index.js"]
