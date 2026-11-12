import { Router } from 'express';
import { pool } from '../config/db.js';

/**
 * Read-only evaluation API for the WebArena-Pro evaluator.
 *
 * Exposes backend state (songs, playlists with resolved song titles,
 * favorites) as JSON so music-app tasks can be graded deterministically
 * instead of relying on an LLM judge. Rows are name-resolved so checks never
 * need UUID joins.
 *
 * Strictly read-only. Gated by a secret token (WP_EVAL_TOKEN) that the agent
 * under test never sees, so it cannot read answers. Disabled (403) when
 * WP_EVAL_TOKEN is unset.
 *
 * Usage:  GET /api/eval/state
 *         header  X-Eval-Token: <WP_EVAL_TOKEN>
 */

const router = Router();

router.get('/state', async (req, res) => {
  const token = process.env.WP_EVAL_TOKEN;
  if (!token || req.get('X-Eval-Token') !== token) {
    return res.status(403).json({ error: 'forbidden' });
  }

  try {
    const songs = await pool.query(`
      SELECT s.title, ar.name AS artist, al.title AS album, s.duration, s.genre
        FROM songs s
        JOIN artists ar ON ar.id = s.artist_id
        LEFT JOIN albums al ON al.id = s.album_id
       ORDER BY s.title`);
    const playlists = await pool.query(`
      SELECT p.name, p.user_id,
             COALESCE(SUM(s.duration), 0)::int AS total_duration,
             COUNT(ps.song_id)::int AS song_count
        FROM playlists p
        LEFT JOIN playlist_songs ps ON ps.playlist_id = p.id
        LEFT JOIN songs s ON s.id = ps.song_id
       GROUP BY p.id
       ORDER BY p.name`);
    const playlistSongs = await pool.query(`
      SELECT p.name AS playlist, s.title AS song, s.duration, ps.position
        FROM playlist_songs ps
        JOIN playlists p ON p.id = ps.playlist_id
        JOIN songs s ON s.id = ps.song_id
       ORDER BY p.name, ps.position`);
    const favorites = await pool.query(`
      SELECT f.user_id, s.title AS song
        FROM user_favorites f
        JOIN songs s ON s.id = f.song_id
       ORDER BY s.title`);

    res.json({
      songs: songs.rows,
      playlists: playlists.rows,
      playlist_songs: playlistSongs.rows,
      favorites: favorites.rows,
    });
  } catch (error) {
    res.status(502).json({ error: 'db query failed' });
  }
});

export default router;
