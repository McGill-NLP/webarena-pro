# yt-lite

Local video assets are stored in the Hugging Face dataset repo `WebArena-Pro/yt-lite-data` instead of Git.

Recommended non-Docker setup:

```powershell
pip install flask werkzeug huggingface_hub
python fetch_assets.py
python app.py
```

This fetch step populates:

- `static/videos`
- `static/thumbnails`

If the dataset requires authentication, set `HF_TOKEN` first or pass `--token`.

You can preview what would be downloaded without fetching bytes:

```powershell
python fetch_assets.py --dry-run
```

Docker note:

- `.dockerignore` excludes the large media directories and local database from the build context.
- Do not include the 28GB local media assets in the Docker build context.
- The Dockerfile downloads assets during the image build. Build it from the repo root with a Hugging Face token secret:

```bash
export HF_TOKEN=hf_...
docker build --secret id=hf_token,env=HF_TOKEN -t yt-lite websites/yt-lite
```

## Evaluator image compatibility

Before releasing an image, run the [authenticated evaluator image gate](../../docs/source/evaluator-images.md) against an isolated container. A successful source build does not verify the published Docker Hub image.

## Video filters

Duration filters compare numeric playback length: under 4 minutes, 4 through 20
minutes (inclusive), and over 20 minutes.

Run the regression tests with `python -m unittest discover -s tests -v`.

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
