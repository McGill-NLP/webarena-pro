import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/browse/new-releases', async (req, res) => {
  try {
    const { limit = 20 } = req.query;
    const { rows } = await pool.query(`
      SELECT al.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url) AS artist
      FROM albums al
      LEFT JOIN artists ar ON al.artist_id = ar.id
      ORDER BY al.release_date DESC
      LIMIT $1
    `, [parseInt(limit)]);
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching new releases:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/', async (req, res) => {
  try {
    const { search, genre, artist_id, limit = 50, offset = 0, sort = 'release_date' } = req.query;
    const allowedSorts = { release_date: 'DESC', title: 'ASC', created_at: 'DESC' };
    const sortCol = allowedSorts[sort] !== undefined ? sort : 'release_date';
    const sortDir = allowedSorts[sortCol];

    const conditions = [];
    const params = [];

    if (search) { params.push(`%${search}%`); conditions.push(`al.title ILIKE $${params.length}`); }
    if (genre) { params.push(genre); conditions.push(`al.genre = $${params.length}`); }
    if (artist_id) { params.push(artist_id); conditions.push(`al.artist_id = $${params.length}`); }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), parseInt(offset));

    const { rows } = await pool.query(`
      SELECT al.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url) AS artist
      FROM albums al
      LEFT JOIN artists ar ON al.artist_id = ar.id
      ${where}
      ORDER BY al.${sortCol} ${sortDir}
      LIMIT $${params.length - 1} OFFSET $${params.length}
    `, params);

    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching albums:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id/tracks', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT * FROM songs WHERE album_id = $1 ORDER BY track_number ASC', [req.params.id]);
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    console.error('Error fetching album tracks:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows: albumRows } = await pool.query(`
      SELECT al.*,
        json_build_object('id', ar.id, 'name', ar.name, 'avatar_url', ar.avatar_url, 'country', ar.country) AS artist
      FROM albums al
      LEFT JOIN artists ar ON al.artist_id = ar.id
      WHERE al.id = $1
    `, [id]);

    if (!albumRows[0]) return res.status(404).json({ success: false, error: 'Album not found' });

    const { rows: tracks } = await pool.query('SELECT * FROM songs WHERE album_id = $1 ORDER BY track_number ASC', [id]);
    res.json({ success: true, data: { ...albumRows[0], tracks } });
  } catch (error) {
    console.error('Error fetching album:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { title, artist_id, cover_url, release_date, genre, description, label, license, attribution, source_url, requires_attribution } = req.body;
    if (!title || !artist_id) return res.status(400).json({ success: false, error: 'title and artist_id are required' });

    const { rows } = await pool.query(
      'INSERT INTO albums (title, artist_id, cover_url, release_date, genre, description, label, license, attribution, source_url, requires_attribution) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *',
      [title, artist_id, cover_url, release_date, genre, description, label, license, attribution, source_url, requires_attribution ?? false]
    );
    res.status(201).json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error creating album:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.put('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const fields = ['title', 'cover_url', 'release_date', 'genre', 'description', 'label', 'license', 'attribution', 'source_url', 'requires_attribution'];
    const sets = [];
    const params = [];

    for (const f of fields) {
      if (req.body[f] !== undefined) { params.push(req.body[f]); sets.push(`${f} = $${params.length}`); }
    }
    if (!sets.length) return res.status(400).json({ success: false, error: 'No fields to update' });

    params.push(id);
    const { rows } = await pool.query(`UPDATE albums SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`, params);
    if (!rows[0]) return res.status(404).json({ success: false, error: 'Album not found' });
    res.json({ success: true, data: rows[0] });
  } catch (error) {
    console.error('Error updating album:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await pool.query('DELETE FROM albums WHERE id = $1', [req.params.id]);
    res.json({ success: true, message: 'Album deleted successfully' });
  } catch (error) {
    console.error('Error deleting album:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

export default router;
