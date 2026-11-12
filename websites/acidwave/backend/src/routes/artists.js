import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const { search, genre, limit = 50, offset = 0, include_albums = 'false' } = req.query;
    const conditions = [];
    const params = [];

    if (search) { params.push(`%${search}%`); conditions.push(`a.name ILIKE $${params.length}`); }
    if (genre) { params.push(genre); conditions.push(`$${params.length} = ANY(a.genres)`); }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), parseInt(offset));

    const { rows } = await pool.query(`
      SELECT a.*,
        (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) AS albums_count,
        (SELECT COUNT(*) FROM songs WHERE artist_id = a.id) AS songs_count
      FROM artists a
      ${where}
      ORDER BY a.name ASC
      LIMIT $${params.length - 1} OFFSET $${params.length}
    `, params);

    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching artists:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows: artistRows } = await pool.query('SELECT * FROM artists WHERE id = $1', [id]);
    if (!artistRows[0]) return res.status(404).json({ success: false, error: 'Artist not found' });

    const { rows: albums } = await pool.query('SELECT * FROM albums WHERE artist_id = $1 ORDER BY release_date DESC', [id]);
    const { rows: topSongs } = await pool.query('SELECT * FROM songs WHERE artist_id = $1 ORDER BY plays DESC LIMIT 10', [id]);

    res.json({ success: true, data: { ...artistRows[0], albums, top_songs: topSongs } });
  } catch (error) {
    console.error('Error fetching artist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id/albums', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT * FROM albums WHERE artist_id = $1 ORDER BY release_date DESC', [req.params.id]);
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching artist albums:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id/songs', async (req, res) => {
  try {
    const { limit = 50 } = req.query;
    const { rows } = await pool.query(`
      SELECT s.*,
        CASE WHEN al.id IS NOT NULL THEN json_build_object('id', al.id, 'title', al.title, 'cover_url', al.cover_url) ELSE NULL END AS album
      FROM songs s
      LEFT JOIN albums al ON s.album_id = al.id
      WHERE s.artist_id = $1
      ORDER BY s.plays DESC
      LIMIT $2
    `, [req.params.id, parseInt(limit)]);
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching artist songs:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { name, bio, avatar_url, genres, country, website_url, social_links } = req.body;
    if (!name) return res.status(400).json({ success: false, error: 'Artist name is required' });

    const { rows } = await pool.query(
      'INSERT INTO artists (name, bio, avatar_url, genres, country, website_url, social_links) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *',
      [name, bio, avatar_url, genres, country, website_url, social_links ? JSON.stringify(social_links) : null]
    );
    res.status(201).json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error creating artist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.put('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const fields = ['name', 'bio', 'avatar_url', 'genres', 'country', 'website_url', 'social_links'];
    const sets = [];
    const params = [];

    for (const f of fields) {
      if (req.body[f] !== undefined) { params.push(req.body[f]); sets.push(`${f} = $${params.length}`); }
    }
    if (!sets.length) return res.status(400).json({ success: false, error: 'No fields to update' });

    params.push(id);
    const { rows } = await pool.query(`UPDATE artists SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`, params);
    if (!rows[0]) return res.status(404).json({ success: false, error: 'Artist not found' });
    res.json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error updating artist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await pool.query('DELETE FROM artists WHERE id = $1', [req.params.id]);
    res.json({ success: true, message: 'Artist deleted successfully' });
  } catch (error) {
    console.error('Error deleting artist:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

export default router;
