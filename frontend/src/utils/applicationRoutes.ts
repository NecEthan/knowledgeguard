export const applicationRoutes = {
  login: "/login",
  register: "/register",
  documents: "/documents",
} as const;

export type ApplicationRoute =
  (typeof applicationRoutes)[keyof typeof applicationRoutes];
