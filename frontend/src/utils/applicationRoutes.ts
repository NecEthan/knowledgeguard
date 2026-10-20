export const applicationRoutes = {
  login: "/login",
  documents: "/documents",
  search: "/search",
  audit: "/audit",
} as const;

export type ApplicationRoute =
  (typeof applicationRoutes)[keyof typeof applicationRoutes];
