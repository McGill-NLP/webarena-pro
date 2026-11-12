import express from 'express';
import { readFile } from 'fs/promises';
import { pool } from '../config/db.js';

const router = express.Router();
const SEED_SQL_PATH = process.env.SEED_SQL_PATH || '/tmp/seed.sql';

router.post('/', async (req, res) => {
  const client = await pool.connect();
  try {
    const seedSql = await readFile(SEED_SQL_PATH, 'utf8');
    await client.query('BEGIN');
    await client.query(`
      TRUNCATE TABLE
        user_favorites,
        playlist_songs,
        playlists,
        songs,
        albums,
        artists
      RESTART IDENTITY CASCADE
    `);
    await client.query(seedSql);
    await client.query('COMMIT');

    const { rows } = await client.query('SELECT COUNT(*)::int AS count FROM songs');
    res.json({ status: 'ok', songs: rows[0].count });
  } catch (error) {
    await client.query('ROLLBACK').catch(() => {});
    console.error('Error resetting acidwave state:', error);
    res.status(500).json({ status: 'error', error: error.message });
  } finally {
    client.release();
  }
});

export default router;
