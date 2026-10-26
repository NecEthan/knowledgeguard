export const applicationRoutes = {
  login: "/login",
  documents: "/documents",
  search: "/search",
} as const;

export type ApplicationRoute =
  (typeof applicationRoutes)[keyof typeof applicationRoutes];
