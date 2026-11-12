import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const HF_DATASET_REPO = "WebArena-Pro/acidwave-data";
const HF_RESOLVE_BASE = `https://huggingface.co/datasets/${HF_DATASET_REPO}/resolve/main`;
const SEED_SQL_PATH = "database/seed.sql";
const PUBLIC_AUDIO_PREFIX = "/audio/";
const OUTPUT_ROOT = "acidwave-app/public";

async function getToken() {
  if (process.env.HF_TOKEN) return process.env.HF_TOKEN;
  if (process.env.HUGGINGFACE_TOKEN) return process.env.HUGGINGFACE_TOKEN;

  try {
    return (await readFile("/run/secrets/hf_token", "utf8")).trim();
  } catch {
    return "";
  }
}

function extractAudioPaths(seedSql) {
  const matches = seedSql.matchAll(/'\/audio\/([^']+\.mp3)'/g);
  return [...new Set([...matches].map((match) => `audio/${match[1]}`))];
}

async function downloadAudio(audioPath, token) {
  const sourceUrl = `${HF_RESOLVE_BASE}/${audioPath}`;
  const response = await fetch(sourceUrl, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  if (!response.ok) {
    throw new Error(
      `Failed to download ${sourceUrl}: ${response.status} ${response.statusText}`
    );
  }

  const outputPath = join(OUTPUT_ROOT, audioPath);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, Buffer.from(await response.arrayBuffer()));
}

const token = await getToken();
if (!token) {
  throw new Error("HF_TOKEN is required to download Acidwave audio from Hugging Face.");
}

const seedSql = await readFile(SEED_SQL_PATH, "utf8");
const audioPaths = extractAudioPaths(seedSql).filter((path) =>
  path.startsWith(PUBLIC_AUDIO_PREFIX.slice(1))
);

if (audioPaths.length === 0) {
  throw new Error(`No ${PUBLIC_AUDIO_PREFIX} MP3 paths found in ${SEED_SQL_PATH}.`);
}

await Promise.all(audioPaths.map((audioPath) => downloadAudio(audioPath, token)));

console.log(`Downloaded ${audioPaths.length} Acidwave audio files from ${HF_DATASET_REPO}.`);
