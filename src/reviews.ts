import * as fs from "fs";
import * as path from "path";

export type Rating = "hard" | "medium" | "easy";

export interface ProblemEntry {
  slug: string;
  title: string;
  difficulty: string;
  url: string;
  rating: Rating;
  attempts: number;
  firstSolved: string;
  lastAttempt: string;
}

export interface ReviewsFile {
  version: number;
  problems: Record<string, ProblemEntry>;
}

export interface PendingEntry {
  slug: string;
  title: string;
  difficulty: string;
  url: string;
  at: string;
}

const CURRENT_VERSION = 1;

export function reviewsPath(workspaceRoot: string): string {
  return path.join(workspaceRoot, ".leetknight", "reviews.json");
}

export function loadReviews(workspaceRoot: string): ReviewsFile {
  const p = reviewsPath(workspaceRoot);
  if (!fs.existsSync(p)) {
    return { version: CURRENT_VERSION, problems: {} };
  }
  const raw = fs.readFileSync(p, "utf8");
  const parsed = JSON.parse(raw) as Partial<ReviewsFile>;
  return {
    version: parsed.version ?? CURRENT_VERSION,
    problems: parsed.problems ?? {},
  };
}

export function saveReviews(workspaceRoot: string, data: ReviewsFile): void {
  const p = reviewsPath(workspaceRoot);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const tmp = p + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + "\n");
  fs.renameSync(tmp, p);
}

/**
 * Called after a Submit-Accepted. Adds a new entry (seeded with rating: "easy"
 * — the modal fires immediately after and overwrites this if the user picks
 * a different rating), or increments attempts + updates lastAttempt for an
 * existing entry (leaving the existing rating alone until the modal resolves).
 */
export function upsertOnSubmit(
  workspaceRoot: string,
  pending: PendingEntry,
): void {
  const data = loadReviews(workspaceRoot);
  const existing = data.problems[pending.slug];
  if (existing) {
    existing.attempts += 1;
    existing.lastAttempt = pending.at;
    existing.title = pending.title;
    existing.difficulty = pending.difficulty;
    existing.url = pending.url;
  } else {
    data.problems[pending.slug] = {
      slug: pending.slug,
      title: pending.title,
      difficulty: pending.difficulty,
      url: pending.url,
      rating: "easy",
      attempts: 1,
      firstSolved: pending.at,
      lastAttempt: pending.at,
    };
  }
  saveReviews(workspaceRoot, data);
}

export function setRating(
  workspaceRoot: string,
  slug: string,
  rating: Rating,
): void {
  const data = loadReviews(workspaceRoot);
  const entry = data.problems[slug];
  if (!entry) return;
  entry.rating = rating;
  saveReviews(workspaceRoot, data);
}

const RATING_ORDER: Rating[] = ["hard", "medium", "easy"];

export interface Grouped {
  hard: ProblemEntry[];
  medium: ProblemEntry[];
  easy: ProblemEntry[];
}

export function allTrackedSorted(workspaceRoot: string): Grouped {
  const data = loadReviews(workspaceRoot);
  const groups: Grouped = { hard: [], medium: [], easy: [] };
  for (const entry of Object.values(data.problems)) {
    groups[entry.rating].push(entry);
  }
  for (const key of RATING_ORDER) {
    groups[key].sort((a, b) => a.lastAttempt.localeCompare(b.lastAttempt));
  }
  return groups;
}

export function randomTrackedSlug(workspaceRoot: string): string | undefined {
  const data = loadReviews(workspaceRoot);
  const slugs = Object.keys(data.problems);
  if (slugs.length === 0) return undefined;
  return slugs[Math.floor(Math.random() * slugs.length)];
}

export function getEntry(
  workspaceRoot: string,
  slug: string,
): ProblemEntry | undefined {
  const data = loadReviews(workspaceRoot);
  return data.problems[slug];
}
