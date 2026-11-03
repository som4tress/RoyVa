/** biome-ignore-all lint/suspicious/noExplicitAny: <middleware.route has a methods property, but it's not there in type for some reason> */
/** biome-ignore-all lint/style/noNonNullAssertion: <we are setting map's value before using it using map.get> */

import type express from "express";

import { logger } from "./logger";
import type { RouteModule } from "./types";

function joinPaths(prefix: string, path: string): string {
  if (!prefix) return path;
  if (path === "/") return prefix;
  return `${prefix}${path}`;
}

function splitSegments(path: string): string[] {
  return path.split("/").filter(Boolean);
}

/**
 * Does `requestPath` correspond to one of this app's registered `routePaths`?
 *
 * A plain set lookup isn't enough because routes carry params: `/auth/oauth/github/
 * callback` must be recognised as the registered `/auth/oauth/:provider/callback`.
 * So paths are compared segment by segment, with a `:param` segment matching any
 * single segment.
 *
 * This only answers "is this a route we define?" — it is not a router and does not
 * resolve which handler runs or whether the method matches.
 */
export function isRegisteredRoute(
  requestPath: string,
  routePaths: readonly string[],
): boolean {
  const requestSegments = splitSegments(requestPath);

  return routePaths.some((routePath) => {
    const routeSegments = splitSegments(routePath);
    if (routeSegments.length !== requestSegments.length) {
      return false;
    }

    return routeSegments.every(
      (segment, i) => segment.startsWith(":") || segment === requestSegments[i],
    );
  });
}

/**
 * Walks the Express router stack and returns every registered route path mapped
 * to the HTTP methods it accepts. Shared by `printRoutes` (startup banner) and
 * the request logger (deciding whether a 404 hit a real route or a scanner path).
 *
 * @param app - The Express application instance.
 * @param routes - The route modules mounted on the app. Explicitly needed because prefix info is not available against a router.
 */
export function collectRoutes(
  app: ReturnType<typeof express>,
  routes: readonly RouteModule[] = [],
): Map<string, string[]> {
  const prefixByRouter = new Map<unknown, string>();
  for (const { router, prefix } of routes) {
    prefixByRouter.set(router, prefix);
  }

  const routeMap = new Map<string, string[]>();

  // Iterate through the router stack to collect routes (Express v5 compatible)
  const stack = app.router.stack;

  stack.forEach((middleware) => {
    if (middleware.route) {
      // Routes registered directly on the app
      const methods = Object.keys((middleware.route as any).methods)
        .filter((method) => (middleware.route as any).methods[method])
        .map((method) => method.toUpperCase());

      const path = middleware.route.path;
      if (!routeMap.has(path)) {
        routeMap.set(path, []);
      }
      routeMap.get(path)!.push(...methods);
    } else if (middleware.name === "router") {
      // Routes from mounted routers. Routers mounted at the root have no
      // prefix, so they fall back to "".
      const prefix = prefixByRouter.get(middleware.handle) ?? "";

      (middleware.handle as any).stack.forEach((handler: any) => {
        if (handler.route) {
          const methods = Object.keys(handler.route.methods)
            .filter((method) => handler.route.methods[method])
            .map((method) => method.toUpperCase());

          const paths = Array.isArray(handler.route.path)
            ? handler.route.path
            : [handler.route.path];

          paths.forEach((routePath: string) => {
            const path = joinPaths(prefix, routePath);
            if (!routeMap.has(path)) {
              routeMap.set(path, []);
            }

            routeMap.get(path)!.push(...methods);
          });
        }
      });
    }
  });

  // Remove duplicates from method arrays and sort
  for (const [path, methods] of routeMap) {
    const uniqueMethods = [...new Set(methods)].sort();
    routeMap.set(path, uniqueMethods);
  }

  return routeMap;
}

/**
 * Function to print all registered routes in a pretty format.
 * @param app - The Express application instance.
 * @param routes - The route modules mounted on the app. Explicitly Needed because prefix info is not available against a router.
 */
export function printRoutes(
  app: ReturnType<typeof express>,
  routes: readonly RouteModule[] = [],
): void {
  logger.info("Registered Routes:");
  logger.info("─".repeat(60));

  // Sort routes by path for better readability
  const sortedRoutes = Array.from(collectRoutes(app, routes).entries()).sort(
    ([a], [b]) => a.localeCompare(b),
  );

  // Print routes with their methods
  sortedRoutes.forEach(([path, methods]) => {
    logger.info(`${path}: [${methods.join(", ")}]`);
  });

  logger.info("─".repeat(60));
  logger.info(`Total routes: ${sortedRoutes.length}\n`);
}
