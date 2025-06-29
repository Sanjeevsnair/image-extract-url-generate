# Use an official Node.js runtime as base
FROM node:18

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the entire app codebase
COPY . .

# Ensure required folders exist (or let your app handle it)
RUN mkdir -p ./upload ./images

# Expose port (match the one your app uses)
EXPOSE 3000

# Start the server
CMD ["node", "server.js"]
