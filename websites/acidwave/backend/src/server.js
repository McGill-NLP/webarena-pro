import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import dotenv from 'dotenv';
import { testConnection } from './config/db.js';

import artistsRouter from './routes/artists.js';
import albumsRouter from './routes/albums.js';
import songsRouter from './routes/songs.js';
import playlistsRouter from './routes/playlists.js';
import favoritesRouter from './routes/favorites.js';
import healthRouter from './routes/health.js';
import resetRouter from './routes/reset.js';
import streamRouter from './routes/stream.js';
import evalRouter from './routes/eval.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(morgan('dev'));

app.use('/api/health', healthRouter);
app.use('/api/reset', resetRouter);
app.use('/api/artists', artistsRouter);
app.use('/api/albums', albumsRouter);
app.use('/api/songs', songsRouter);
app.use('/api/playlists', playlistsRouter);
app.use('/api/favorites', favoritesRouter);
app.use('/api/stream', streamRouter);
app.use('/api/eval', evalRouter);

app.get('/', (req, res) => {
  res.json({ message: 'acidwave API', version: '2.0.0' });
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Something went wrong!', message: process.env.NODE_ENV === 'development' ? err.message : undefined });
});

app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

async function startServer() {
  await testConnection();
  app.listen(PORT, () => {
    console.log(`\n🚀 Server running on port ${PORT}`);
  });
}

startServer();
