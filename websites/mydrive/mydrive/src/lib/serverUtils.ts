// Server-side helpers shared by the file/folder API routes.
//
// NOTE: this file was reconstructed — the original src/lib/ directory was
// swallowed by the repo-root .gitignore's `lib/` rule and never committed.

/**
 * Return `name` if it is not taken, otherwise append " (n)" before the
 * extension (Drive-style) until the name is unique within `existingNames`.
 */
export function getUniqueName(name: string, existingNames: Set<string>): string {
  if (!existingNames.has(name)) return name;

  const dot = name.lastIndexOf(".");
  const hasExtension = dot > 0; // a leading dot (".bashrc") is not an extension
  const base = hasExtension ? name.slice(0, dot) : name;
  const extension = hasExtension ? name.slice(dot) : "";

  for (let n = 1; ; n++) {
    const candidate = `${base} (${n})${extension}`;
    if (!existingNames.has(candidate)) return candidate;
  }
}
