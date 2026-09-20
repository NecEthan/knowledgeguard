FROM node:20-alpine

WORKDIR /app

# Install dependencies (cached layer — only rebuilds when package files change)
COPY package*.json ./
RUN npm install

# Copy application code
COPY . .

EXPOSE 3000

ENV NEXT_TELEMETRY_DISABLED=1

CMD ["npm", "run", "dev"]
