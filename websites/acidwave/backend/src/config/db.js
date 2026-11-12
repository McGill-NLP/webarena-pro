import pg from 'pg';
import dotenv from 'dotenv';

dotenv.config();

const { Pool } = pg;

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://postgres@localhost/acidwave'
});

export async function testConnection() {
  try {
    const { rows } = await pool.query('SELECT COUNT(*) FROM songs');
    console.log(`✅ PostgreSQL connected (${rows[0].count} songs)`);
    return true;
  } catch (error) {
    console.error('❌ PostgreSQL connection error:', error.message);
    return false;
  }
}
