import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const { search, genre, artist_id, album_id, limit = 50, offset = 0, sort = 'created_at' } = req.query;

    const allowedSorts = { title: 'ASC', created_at: 'DESC', plays: 'DESC', likes: 'DESC' };
    const sortCol = allowedSorts[sort] ? sort : 'created_at';
    const sortDir = allowedSorts[sortCol];

    const conditions = [];
    const params = [];

    if (search) { params.push(`%${search}%`); conditions.push(`s.title ILIKE $${params.length}`); }
    if (genre) { params.push(genre); conditions.push(`s.genre = $${params.length}`); }
    if (artist_id) { params.push(artist_id); conditions.push(`s.artist_id = $${params.length}`); }
    if (album_id) { params.push(album_id); conditions.push(`s.album_id = $${params.length}`); }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), parseInt(offset));

    const { rows } = await pool.query(`
      SELECT s.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url) AS artist,
        CASE WHEN al.id IS NOT NULL THEN json_build_object('id', al.id, 'title', al.title, 'cover_url', al.cover_url) ELSE NULL END AS album
      FROM songs s
      LEFT JOIN artists ar ON s.artist_id = ar.id
      LEFT JOIN albums al ON s.album_id = al.id
      ${where}
      ORDER BY s.${sortCol} ${sortDir}
      LIMIT $${params.length - 1} OFFSET $${params.length}
    `, params);

    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching songs:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows } = await pool.query(`
      SELECT s.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url, 'country', ar.country) AS artist,
        CASE WHEN al.id IS NOT NULL THEN json_build_object('id', al.id, 'title', al.title, 'cover_url', al.cover_url, 'release_date', al.release_date) ELSE NULL END AS album
      FROM songs s
      LEFT JOIN artists ar ON s.artist_id = ar.id
      LEFT JOIN albums al ON s.album_id = al.id
      WHERE s.id = $1
    `, [id]);

    if (!rows[0]) return res.status(404).json({ success: false, error: 'Song not found' });
    res.json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error fetching song:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { title, artist_id, album_id, track_number, duration, url, cover_url, genre, release_date, lyrics, license, attribution, source_url, requires_attribution, is_explicit } = req.body;

    if (!title || !artist_id || !duration || !url) {
      return res.status(400).json({ success: false, error: 'title, artist_id, duration, and url are required' });
    }

    const { rows } = await pool.query(`
      INSERT INTO songs (title, artist_id, album_id, track_number, duration, url, cover_url, genre, release_date, lyrics, license, attribution, source_url, requires_attribution, is_explicit)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
      RETURNING *
    `, [title, artist_id, album_id, track_number, duration, url, cover_url, genre, release_date, lyrics, license, attribution, source_url, requires_attribution ?? false, is_explicit ?? false]);

    res.status(201).json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error creating song:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.put('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const fields = ['title', 'album_id', 'track_number', 'duration', 'url', 'cover_url', 'genre', 'release_date', 'lyrics', 'plays', 'likes', 'license', 'attribution', 'source_url', 'requires_attribution', 'is_explicit'];
    const sets = [];
    const params = [];

    for (const f of fields) {
      if (req.body[f] !== undefined) { params.push(req.body[f]); sets.push(`${f} = $${params.length}`); }
    }
    if (!sets.length) return res.status(400).json({ success: false, error: 'No fields to update' });

    params.push(id);
    const { rows } = await pool.query(`UPDATE songs SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`, params);
    if (!rows[0]) return res.status(404).json({ success: false, error: 'Song not found' });
    res.json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error updating song:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await pool.query('DELETE FROM songs WHERE id = $1', [req.params.id]);
    res.json({ success: true, message: 'Song deleted successfully' });
  } catch (error) {
    console.error('Error deleting song:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

export default router;
