// Fails the build if a translation key exists in one language and not the other (PRD section 9).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const sets = [
  { name: "frontend", dir: join(here, "..", "src", "i18n") },
  { name: "backend", dir: join(here, "..", "..", "backend", "app", "i18n") },
];
const langs = ["en", "ta"];

function flatten(obj, prefix = "") {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" ? flatten(v, `${prefix}${k}.`) : [[`${prefix}${k}`, v]],
  );
}

let failed = false;
for (const set of sets) {
  const maps = Object.fromEntries(
    langs.map((l) => [l, new Map(flatten(JSON.parse(readFileSync(join(set.dir, `${l}.json`), "utf8"))))]),
  );
  for (const a of langs) {
    for (const b of langs) {
      if (a === b) continue;
      for (const key of maps[a].keys()) {
        if (!maps[b].has(key)) {
          console.error(`[${set.name}] "${key}" is in ${a}.json but missing from ${b}.json`);
          failed = true;
        }
      }
    }
    for (const [key, value] of maps[a]) {
      if (typeof value !== "string" || !value.trim()) {
        console.error(`[${set.name}] "${key}" in ${a}.json is empty`);
        failed = true;
      }
    }
  }
  // Placeholders must match between languages.
  for (const [key, value] of maps.en) {
    const other = maps.ta.get(key);
    if (typeof other !== "string") continue;
    const ph = (s) => [...s.matchAll(/\{\{?\s*(\w+)\s*\}?\}/g)].map((m) => m[1]).sort().join(",");
    if (ph(value) !== ph(other)) {
      console.error(`[${set.name}] "${key}" placeholders differ: en(${ph(value)}) ta(${ph(other)})`);
      failed = true;
    }
  }
  console.log(`[${set.name}] ${maps.en.size} keys checked`);
}

// Every literal key used in the code must exist (catches t("app.show") with no translation).
function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : /\.(tsx?|jsx?)$/.test(name) ? [p] : [];
  });
}
const en = new Map(flatten(JSON.parse(readFileSync(join(sets[0].dir, "en.json"), "utf8"))));
const pluralBase = new Set([...en.keys()].map((k) => k.replace(/_(one|other)$/, "")));
let missing = 0;
for (const file of walk(join(here, "..", "src"))) {
  const text = readFileSync(file, "utf8");
  for (const m of text.matchAll(/\bt\(\s*"([a-zA-Z][\w]*(?:\.[\w]+)+)"/g)) {
    if (!en.has(m[1]) && !pluralBase.has(m[1])) {
      console.error(`[frontend] ${file.split("/src/")[1]} uses "${m[1]}", which is not in en.json`);
      missing += 1;
    }
  }
}
console.log(`[frontend] literal keys in code checked`);
process.exit(failed || missing ? 1 : 0);
