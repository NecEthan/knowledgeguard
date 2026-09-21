export const applicationRoutes = {
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
} as const;

export type ApplicationRoute =
  (typeof applicationRoutes)[keyof typeof applicationRoutes];
