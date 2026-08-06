/**
 * flakiness-middleware.ts
 *
 * Controlled flakiness injection for MSc dissertation research.
 * AI-Assisted Flaky Test Detection in CI/CD Pipelines — Ubaid Ali, A00046299
 *
 * This middleware introduces realistic non-deterministic behaviour into the
 * RWA backend API to create measurable flaky test conditions for the experiment.
 *
 * Injection types:
 *   - Slow responses: 30% chance of 2,000–4,500ms delay on key GET endpoints
 *   - Server errors:  20% chance of 500 response on key POST endpoints
 *
 * To disable: set FLAKY_ENABLED=false in environment, or remove the middleware
 * registration from app.ts. All injected behaviour is logged with [FLAKY] prefix.
 */

import { Request, Response, NextFunction } from "express";

const FLAKY_ENABLED = process.env.FLAKY_ENABLED !== "false";

const SLOW_PROBABILITY  = 0.30; // 30% chance of slow response
const ERROR_PROBABILITY = 0.20; // 20% chance of 500 error on POST

const SLOW_MIN_MS = 2000;
const SLOW_MAX_MS = 4500;

// Endpoints that receive slow-response injection (GET only)
const SLOW_ENDPOINTS = [
  "/api/transactions",
  "/api/notifications",
  "/api/contacts",
  "/api/bankaccounts",
];

// Endpoints that receive random 500-error injection (POST only)
const ERROR_ENDPOINTS = [
  "/api/transactions",
  "/api/bankaccounts",
  "/api/comments",
  "/api/likes",
];

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function shouldTrigger(probability: number): boolean {
  return FLAKY_ENABLED && Math.random() < probability;
}

/**
 * Slow-response middleware — applied to GET requests on key endpoints.
 * Randomly delays the response to simulate network latency or DB slowness.
 */
export function slowResponseMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (req.method !== "GET") return next();

  const matched = SLOW_ENDPOINTS.some((ep) => req.path.startsWith(ep.replace("/api", "")));
  if (!matched) return next();

  if (shouldTrigger(SLOW_PROBABILITY)) {
    const delay = randomInt(SLOW_MIN_MS, SLOW_MAX_MS);
    console.log(`[FLAKY] Slow response injected on ${req.method} ${req.path} (+${delay}ms)`);
    setTimeout(next, delay);
  } else {
    next();
  }
}

/**
 * Random error middleware — applied to POST requests on key endpoints.
 * Randomly returns a 500 to simulate an unstable backend dependency.
 */
export function randomErrorMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (req.method !== "POST") return next();

  const matched = ERROR_ENDPOINTS.some((ep) => req.path.startsWith(ep.replace("/api", "")));
  if (!matched) return next();

  if (shouldTrigger(ERROR_PROBABILITY)) {
    console.log(`[FLAKY] 500 error injected on ${req.method} ${req.path}`);
    res.status(500).json({
      error: "Flaky server error — injected for dissertation research (A00046299)",
    });
    return;
  }

  next();
}
