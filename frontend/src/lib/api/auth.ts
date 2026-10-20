import type { User } from "@/types";
import { httpClient } from "./client";

export async function register(email: string, password: string): Promise<User> {
  return httpClient<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<User> {
  const user = await httpClient<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  // Set a UI routing hint cookie on this domain so proxy.ts can see it.
  // Not a security token — backend still validates the real session cookie.
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `kg_ui_auth=1; path=/; SameSite=Strict${secure}`;
  return user;
}

export async function logout(): Promise<void> {
  await fetch(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/auth/logout`,
    { method: "POST", credentials: "include" }
  );
  document.cookie = "kg_ui_auth=; path=/; max-age=0";
}

export async function getUser(): Promise<User> {
  return httpClient<User>("/auth/user");
}
