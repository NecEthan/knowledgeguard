"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, logout } from "@/lib/api/auth";
import type { User } from "@/types";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => router.replace(applicationRoutes.login));
  }, [router]);

  async function handleLogout() {
    await logout();
    router.replace(applicationRoutes.login);
  }

  if (!user) {
    return null;
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <span className="text-lg">Signed in as {user.email}</span>
      <Button onClick={handleLogout}>Sign out</Button>
    </main>
  );
}
