import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const { user_id = 'guest' } = req.query;
    const { rows } = await pool.query(`
      SELECT uf.id, uf.song_id, uf.created_at, s.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url) AS artist,
        CASE WHEN al.id IS NOT NULL THEN json_build_object('id', al.id, 'title', al.title, 'cover_url', al.cover_url) ELSE NULL END AS album
      FROM user_favorites uf
      JOIN songs s ON uf.song_id = s.id
      LEFT JOIN artists ar ON s.artist_id = ar.id
      LEFT JOIN albums al ON s.album_id = al.id
      WHERE uf.user_id = $1
      ORDER BY uf.created_at DESC
    `, [user_id]);
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching favorites:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { song_id, user_id = 'guest' } = req.body;
    if (!song_id) return res.status(400).json({ success: false, error: 'song_id is required' });

    const { rows } = await pool.query(
      'INSERT INTO user_favorites (song_id, user_id) VALUES ($1,$2) ON CONFLICT (song_id, user_id) DO NOTHING RETURNING *',
      [song_id, user_id]
    );
    res.status(201).json({ success: true, data: rows[0] || null, message: rows[0] ? undefined : 'Song already in favorites' });
  } catch (error) {
    console.error('Error adding to favorites:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:song_id', async (req, res) => {
  try {
    const { user_id = 'guest' } = req.query;
    await pool.query('DELETE FROM user_favorites WHERE song_id = $1 AND user_id = $2', [req.params.song_id, user_id]);
    res.json({ success: true, message: 'Song removed from favorites successfully' });
  } catch (error) {
    console.error('Error removing from favorites:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/check', async (req, res) => {
  try {
    const { song_id, user_id = 'guest' } = req.body;
    if (!song_id) return res.status(400).json({ success: false, error: 'song_id is required' });

    const { rows } = await pool.query('SELECT id FROM user_favorites WHERE song_id = $1 AND user_id = $2', [song_id, user_id]);
    res.json({ success: true, is_favorited: rows.length > 0 });
  } catch (error) {
    console.error('Error checking favorite:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

export default router;
