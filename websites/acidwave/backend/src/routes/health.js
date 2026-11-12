import express from 'express';
import { pool } from '../config/db.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT COUNT(*) FROM songs');
    res.json({
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      database: { connected: true, songs_count: parseInt(rows[0].count) }
    });
  } catch (error) {
    res.status(503).json({
      status: 'error',
      message: 'Service unavailable',
      database: { connected: false, error: error.message }
    });
  }
});

export default router;
