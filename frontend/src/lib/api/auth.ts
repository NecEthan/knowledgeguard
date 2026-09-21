import type { User } from "@/types";
import { httpClient } from "./client";

export async function register(email: string, password: string): Promise<User> {
  return httpClient<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<User> {
  return httpClient<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await fetch(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/auth/logout`,
    { method: "POST", credentials: "include" }
  );
}

export async function getMe(): Promise<User> {
  return httpClient<User>("/auth/me");
}
