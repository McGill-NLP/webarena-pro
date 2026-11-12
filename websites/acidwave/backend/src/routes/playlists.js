import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const { user_id = 'guest' } = req.query;
    const { rows } = await pool.query(
      'SELECT * FROM playlists WHERE user_id = $1 ORDER BY created_at DESC',
      [user_id]
    );
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching playlists:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows: plRows } = await pool.query('SELECT * FROM playlists WHERE id = $1', [id]);
    if (!plRows[0]) return res.status(404).json({ success: false, error: 'Playlist not found' });

    const { rows: songs } = await pool.query(`
      SELECT ps.position, ps.added_at, s.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url) AS artist,
        CASE WHEN al.id IS NOT NULL THEN json_build_object('id', al.id, 'title', al.title, 'cover_url', al.cover_url) ELSE NULL END AS album
      FROM playlist_songs ps
      JOIN songs s ON ps.song_id = s.id
      LEFT JOIN artists ar ON s.artist_id = ar.id
      LEFT JOIN albums al ON s.album_id = al.id
      WHERE ps.playlist_id = $1
      ORDER BY ps.position ASC
    `, [id]);

    res.json({ success: true, data: { ...plRows[0], playlist_songs: songs } });
  } catch (error) {
    console.error('Error fetching playlist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { name, description, cover_url, is_public, user_id = 'guest' } = req.body || {};
    if (!name || !String(name).trim()) {
      return res.status(400).json({ success: false, error: 'name is required' });
    }

    const { rows } = await pool.query(
      'INSERT INTO playlists (user_id, name, description, cover_url, is_public) VALUES ($1,$2,$3,$4,$5) RETURNING *',
      [user_id, String(name).trim(), description || null, cover_url || null, is_public ?? true]
    );
    res.status(201).json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error creating playlist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/:id/songs', async (req, res) => {
  try {
    const { id } = req.params;
    const { song_id, position } = req.body || {};
    if (!song_id) {
      return res.status(400).json({ success: false, error: 'song_id is required' });
    }

    const { rows: playlistRows } = await pool.query('SELECT id FROM playlists WHERE id = $1', [id]);
    if (!playlistRows[0]) {
      return res.status(404).json({ success: false, error: 'Playlist not found' });
    }

    const { rows: songRows } = await pool.query('SELECT id FROM songs WHERE id = $1', [song_id]);
    if (!songRows[0]) {
      return res.status(404).json({ success: false, error: 'Song not found' });
    }

    let nextPosition = position;
    if (nextPosition === undefined || nextPosition === null) {
      const { rows: positionRows } = await pool.query(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM playlist_songs WHERE playlist_id = $1',
        [id]
      );
      nextPosition = positionRows[0].next_position;
    }

    const { rows } = await pool.query(
      'INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES ($1,$2,$3) ON CONFLICT (playlist_id, song_id) DO NOTHING RETURNING *',
      [id, song_id, nextPosition]
    );
    res.status(201).json({ success: true, data: rows[0] || null });
  } catch (error) {
    console.error('Error adding song to playlist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:id/songs/:song_id', async (req, res) => {
  try {
    await pool.query('DELETE FROM playlist_songs WHERE playlist_id = $1 AND song_id = $2', [req.params.id, req.params.song_id]);
    res.json({ success: true, message: 'Song removed from playlist successfully' });
  } catch (error) {
    console.error('Error removing song from playlist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await pool.query('DELETE FROM playlists WHERE id = $1', [req.params.id]);
    res.json({ success: true, message: 'Playlist deleted successfully' });
  } catch (error) {
    console.error('Error deleting playlist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

export default router;
