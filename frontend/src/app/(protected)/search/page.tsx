"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { QueryResponse } from "@/types";
import { runQuery } from "@/lib/api/query";
import { ApiError } from "@/lib/api/client";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

export default function SearchPage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<"current" | "historical">("current");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const response = await runQuery({ question: question.trim(), mode });
      setResult(response);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          router.replace(applicationRoutes.login);
          return;
        }
        if (err.status === 503) {
          setError(
            "The AI service is temporarily unavailable. Please try again later."
          );
        } else {
          setError("Something went wrong. Please try again.");
        }
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center py-12 px-4 gap-8">
      <div className="w-full max-w-2xl">
        <span className="text-2xl font-semibold">Search knowledge base</span>
      </div>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Ask a question</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="question">Question</Label>
              <Input
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What is the annual leave policy?"
                disabled={loading}
              />
            </div>

            <div className="flex gap-2" role="group" aria-label="Version mode">
              <Button
                type="button"
                variant={mode === "current" ? "default" : "outline"}
                onClick={() => setMode("current")}
                disabled={loading}
                aria-pressed={mode === "current"}
              >
                Current
              </Button>
              <Button
                type="button"
                variant={mode === "historical" ? "default" : "outline"}
                onClick={() => setMode("historical")}
                disabled={loading}
                aria-pressed={mode === "historical"}
              >
                Historical
              </Button>
            </div>

            <Button type="submit" disabled={loading || !question.trim()}>
              {loading ? "Searching..." : "Search"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && (
        <Card className="w-full max-w-2xl border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {result && (
        <>
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle>Answer</CardTitle>
            </CardHeader>
            <CardContent>
              <p>{result.answer}</p>
            </CardContent>
          </Card>

          {result.citations.length > 0 ? (
            <Card className="w-full max-w-2xl">
              <CardHeader>
                <CardTitle>Sources</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-3">
                  {result.citations.map((citation, i) => (
                    <li key={i} className="border rounded p-3">
                      <p className="font-medium">{citation.document_title}</p>
                      <p className="text-sm text-muted-foreground">
                        Version {citation.version_number} &middot; {citation.status}{" "}
                        &middot;{" "}
                        {new Date(citation.updated_at).toLocaleDateString()}
                      </p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : (
            <Card className="w-full max-w-2xl">
              <CardContent className="pt-6">
                <p className="text-muted-foreground">No relevant information found.</p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </main>
  );
}
